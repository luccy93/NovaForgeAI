"""Code Intelligence Engine — all SQLAlchemy models."""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


# ─── Enums (plain Python for SQLite compatibility) ──────────────────────


class IndexStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    DISCOVERING = "DISCOVERING"
    PARSING = "PARSING"
    ANALYZING = "ANALYZING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    GRAPHING = "GRAPHING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    STALE = "STALE"


class FileStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    PARSED = "PARSED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"


class SymbolType(str, enum.Enum):
    FILE = "FILE"
    MODULE = "MODULE"
    PACKAGE = "PACKAGE"
    NAMESPACE = "NAMESPACE"
    CLASS = "CLASS"
    INTERFACE = "INTERFACE"
    STRUCT = "STRUCT"
    ENUM = "ENUM"
    FUNCTION = "FUNCTION"
    METHOD = "METHOD"
    VARIABLE = "VARIABLE"
    CONSTANT = "CONSTANT"
    PROPERTY = "PROPERTY"
    TYPE = "TYPE"
    IMPORT = "IMPORT"


class ReferenceType(str, enum.Enum):
    DEFINITION = "DEFINITION"
    REFERENCE = "REFERENCE"
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    INHERITANCE = "INHERITANCE"
    IMPLEMENTATION = "IMPLEMENTATION"
    CALL = "CALL"
    DECORATOR = "DECORATOR"


class Severity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SmellType(str, enum.Enum):
    LONG_FUNCTION = "LONG_FUNCTION"
    GOD_CLASS = "GOD_CLASS"
    DUPLICATE_PATTERN = "DUPLICATE_PATTERN"
    DEAD_CODE = "DEAD_CODE"
    DEEP_NESTING = "DEEP_NESTING"
    HIGH_COUPLING = "HIGH_COUPLING"
    LOW_COHESION = "LOW_COHESION"
    LARGE_PARAMETER_LIST = "LARGE_PARAMETER_LIST"
    UNUSED_IMPORT = "UNUSED_IMPORT"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"
    LONG_PARAMETER_LIST = "LONG_PARAMETER_LIST"
    COMPLEX_FUNCTION = "COMPLEX_FUNCTION"
    DEPRECATED_USAGE = "DEPRECATED_USAGE"
    MAGIC_NUMBER = "MAGIC_NUMBER"
    NESTED_CALLBACK = "NESTED_CALLBACK"


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TestType(str, enum.Enum):
    FILE = "FILE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    FIXTURE = "FIXTURE"
    MOCK = "MOCK"
    CONFTEST = "CONFTEST"


# ─── 1. CodeIndex ───────────────────────────────────────────────────────


class CodeIndex(Base, TimestampMixin):
    __tablename__ = "code_indexes"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=IndexStatus.QUEUED.value,
    )
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    parser_version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    chunker_version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100))
    embedding_version: Mapped[Optional[str]] = mapped_column(String(50))
    embedding_dimension: Mapped[Optional[int]] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    files_total: Mapped[int] = mapped_column(Integer, default=0)
    files_processed: Mapped[int] = mapped_column(Integer, default=0)
    symbols_extracted: Mapped[int] = mapped_column(Integer, default=0)
    chunks_created: Mapped[int] = mapped_column(Integer, default=0)
    embeddings_stored: Mapped[int] = mapped_column(Integer, default=0)
    graph_edges_created: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    @property
    def branch(self):
        return "main"

    @property
    def file_count(self):
        return self.files_total

    @property
    def symbol_count(self):
        return self.symbols_extracted

    @property
    def index_size_bytes(self):
        return 0

    # relationships
    repository: Mapped["Repository"] = relationship()  # noqa: F821
    versions: Mapped[list["CodeIndexVersion"]] = relationship(
        back_populates="index", cascade="all, delete-orphan"
    )
    files: Mapped[list["CodeFile"]] = relationship(
        back_populates="index", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["CodeChunk"]] = relationship(
        back_populates="index", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["CodeIndexJob"]] = relationship(
        back_populates="index", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_code_indexes_repo_id", "repository_id"),
        Index("ix_code_indexes_status", "status"),
        Index("ix_code_indexes_repo_status", "repository_id", "status"),
    )


# ─── 2. CodeIndexVersion ────────────────────────────────────────────────


class CodeIndexVersion(Base):
    __tablename__ = "code_index_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    index_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_indexes.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parser_version: Mapped[Optional[str]] = mapped_column(String(50))
    chunker_version: Mapped[Optional[str]] = mapped_column(String(50))
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100))
    embedding_version: Mapped[Optional[str]] = mapped_column(String(50))
    embedding_dimension: Mapped[Optional[int]] = mapped_column(Integer)
    schema_version: Mapped[Optional[str]] = mapped_column(String(50))
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    rollback_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    @property
    def version(self):
        return self.version_number

    @property
    def status(self):
        return "active" if self.is_active else "inactive"

    @property
    def files_changed(self):
        return 0

    index: Mapped["CodeIndex"] = relationship(back_populates="versions")

    __table_args__ = (
        Index("ix_code_index_versions_index_id", "index_id"),
    )


# ─── 3. CodeFile ────────────────────────────────────────────────────────


class CodeFile(Base, TimestampMixin):
    __tablename__ = "code_files"

    index_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_indexes.id", ondelete="CASCADE"),
        nullable=False,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[Optional[str]] = mapped_column(String(50))
    file_hash: Mapped[Optional[str]] = mapped_column(String(64))
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    line_count: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=FileStatus.QUEUED.value
    )
    parse_error: Mapped[Optional[str]] = mapped_column(Text)
    last_modified_commit: Mapped[Optional[str]] = mapped_column(String(40))
    is_test_file: Mapped[bool] = mapped_column(Boolean, default=False)
    is_config_file: Mapped[bool] = mapped_column(Boolean, default=False)
    is_documentation: Mapped[bool] = mapped_column(Boolean, default=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    symbol_count: Mapped[int] = mapped_column(Integer, default=0)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # relationships
    index: Mapped["CodeIndex"] = relationship(back_populates="files")
    repository: Mapped["Repository"] = relationship()  # noqa: F821
    symbols: Mapped[list["CodeSymbol"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    references: Mapped[list["CodeReference"]] = relationship(
        back_populates="source_file", cascade="all, delete-orphan"
    )
    caller_calls: Mapped[list["CodeCall"]] = relationship(
        back_populates="caller_file", cascade="all, delete-orphan",
        overlaps="callee_calls",
    )
    imports: Mapped[list["CodeImport"]] = relationship(
        back_populates="source_file", cascade="all, delete-orphan"
    )
    metrics: Mapped[list["CodeMetrics"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    smells: Mapped[list["CodeSmell"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    tests: Mapped[list["CodeTest"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["CodeChunk"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )

    @property
    def path(self) -> str:
        return self.file_path

    __table_args__ = (
        Index("ix_code_files_index_path", "index_id", "file_path"),
        Index("ix_code_files_language", "language"),
        Index("ix_code_files_repo_id", "repository_id"),
    )


# ─── 4. CodeSymbol ──────────────────────────────────────────────────────


class CodeSymbol(Base, TimestampMixin):
    __tablename__ = "code_symbols"

    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    index_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_indexes.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol_id: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    symbol_type: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    qualified_name: Mapped[str] = mapped_column(String(1000), nullable=False)
    scope: Mapped[Optional[str]] = mapped_column(String(1000))
    language: Mapped[Optional[str]] = mapped_column(String(50))
    start_line: Mapped[Optional[int]] = mapped_column(Integer)
    end_line: Mapped[Optional[int]] = mapped_column(Integer)
    signature: Mapped[Optional[str]] = mapped_column(Text)
    docstring: Mapped[Optional[str]] = mapped_column(Text)
    visibility: Mapped[Optional[str]] = mapped_column(String(20))
    is_async: Mapped[bool] = mapped_column(Boolean, default=False)
    is_abstract: Mapped[bool] = mapped_column(Boolean, default=False)
    is_static: Mapped[bool] = mapped_column(Boolean, default=False)
    decorators: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    parameters: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    return_type: Mapped[Optional[str]] = mapped_column(String(255))
    parent_symbol_id: Mapped[Optional[str]] = mapped_column(String(500))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    @property
    def line_start(self):
        return self.start_line

    @property
    def line_end(self):
        return self.end_line

    @property
    def column_start(self):
        return 0

    @property
    def column_end(self):
        return 0

    @property
    def complexity(self):
        return 0

    @property
    def parent_id(self):
        if self.parent_symbol_id:
            try:
                return uuid.UUID(self.parent_symbol_id)
            except (ValueError, TypeError):
                return None
        return None

    # relationships
    file: Mapped["CodeFile"] = relationship(back_populates="symbols")
    repository: Mapped["Repository"] = relationship()  # noqa: F821
    index: Mapped["CodeIndex"] = relationship()
    source_references: Mapped[list["CodeReference"]] = relationship(
        back_populates="source_symbol", cascade="all, delete-orphan",
        foreign_keys="[CodeReference.source_symbol_id]",
    )
    target_references: Mapped[list["CodeReference"]] = relationship(
        back_populates="target_symbol", cascade="all, delete-orphan",
        foreign_keys="[CodeReference.target_symbol_id]",
    )
    caller_calls: Mapped[list["CodeCall"]] = relationship(
        back_populates="caller_symbol", cascade="all, delete-orphan",
        foreign_keys="[CodeCall.caller_symbol_id]",
    )
    callee_calls: Mapped[list["CodeCall"]] = relationship(
        back_populates="callee_symbol", cascade="all, delete-orphan",
        foreign_keys="[CodeCall.callee_symbol_id]",
    )
    imported_by: Mapped[list["CodeImport"]] = relationship(
        back_populates="imported_symbol", cascade="all, delete-orphan",
    )
    metrics: Mapped[list["CodeMetrics"]] = relationship(
        back_populates="symbol", cascade="all, delete-orphan"
    )
    smells: Mapped[list["CodeSmell"]] = relationship(
        back_populates="symbol", cascade="all, delete-orphan"
    )
    tests: Mapped[list["CodeTest"]] = relationship(
        back_populates="symbol", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["CodeChunk"]] = relationship(
        back_populates="symbol", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_code_symbols_symbol_id", "symbol_id", unique=True),
        Index("ix_code_symbols_repo_type", "repository_id", "symbol_type"),
        Index("ix_code_symbols_file_type", "file_id", "symbol_type"),
        Index("ix_code_symbols_qualified_name", "qualified_name"),
        Index("ix_code_symbols_name", "name"),
    )


# ─── 5. CodeReference ───────────────────────────────────────────────────


class CodeReference(Base, TimestampMixin):
    __tablename__ = "code_references"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    index_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_indexes.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_symbol_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_symbols.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_symbol_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_symbols.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_line: Mapped[Optional[int]] = mapped_column(Integer)
    source_column: Mapped[Optional[int]] = mapped_column(Integer)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    target_name: Mapped[Optional[str]] = mapped_column(String(500))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    # relationships
    source_symbol: Mapped[Optional["CodeSymbol"]] = relationship(
        foreign_keys=[source_symbol_id], back_populates="source_references"
    )
    target_symbol: Mapped[Optional["CodeSymbol"]] = relationship(
        foreign_keys=[target_symbol_id], back_populates="target_references"
    )
    source_file: Mapped["CodeFile"] = relationship(back_populates="references")

    @property
    def line(self):
        return self.source_line

    @property
    def target_file_id(self):
        return None

    __table_args__ = (
        Index("ix_code_references_source_symbol_type", "source_symbol_id", "reference_type"),
        Index("ix_code_references_target_symbol", "target_symbol_id"),
        Index("ix_code_references_source_file", "source_file_id"),
        Index("ix_code_references_resolved", "resolved"),
    )


# ─── 6. CodeCall ────────────────────────────────────────────────────────


class CodeCall(Base, TimestampMixin):
    __tablename__ = "code_calls"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    index_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_indexes.id", ondelete="CASCADE"),
        nullable=False,
    )
    caller_symbol_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_symbols.id", ondelete="CASCADE"),
        nullable=False,
    )
    callee_symbol_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_symbols.id", ondelete="SET NULL"),
        nullable=True,
    )
    caller_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    callee_name: Mapped[Optional[str]] = mapped_column(String(500))
    call_line: Mapped[Optional[int]] = mapped_column(Integer)
    call_type: Mapped[Optional[str]] = mapped_column(String(30))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    # relationships
    caller_symbol: Mapped["CodeSymbol"] = relationship(
        foreign_keys=[caller_symbol_id], back_populates="caller_calls"
    )
    callee_symbol: Mapped[Optional["CodeSymbol"]] = relationship(
        foreign_keys=[callee_symbol_id], back_populates="callee_calls"
    )
    caller_file: Mapped["CodeFile"] = relationship(
        foreign_keys=[caller_file_id], back_populates="caller_calls"
    )

    @property
    def caller_id(self):
        return self.caller_symbol_id

    @property
    def callee_id(self):
        return self.callee_symbol_id

    @property
    def line(self):
        return self.call_line

    @property
    def caller_name(self):
        return getattr(self, '_caller_name_val', None)

    __table_args__ = (
        Index("ix_code_calls_caller_symbol", "caller_symbol_id"),
        Index("ix_code_calls_callee_symbol", "callee_symbol_id"),
        Index("ix_code_calls_caller_file_type", "caller_file_id", "call_type"),
    )


# ─── 7. CodeImport ──────────────────────────────────────────────────────


class CodeImport(Base, TimestampMixin):
    __tablename__ = "code_imports"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    index_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_indexes.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    imported_name: Mapped[str] = mapped_column(String(1000), nullable=False)
    imported_symbol_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_symbols.id", ondelete="SET NULL"),
        nullable=True,
    )
    import_type: Mapped[str] = mapped_column(String(30), nullable=False)
    alias: Mapped[Optional[str]] = mapped_column(String(255))
    is_external: Mapped[bool] = mapped_column(Boolean, default=False)
    is_stdlib: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    # relationships
    source_file: Mapped["CodeFile"] = relationship(back_populates="imports")
    imported_symbol: Mapped[Optional["CodeSymbol"]] = relationship(
        back_populates="imported_by"
    )

    @property
    def file_id(self):
        return self.source_file_id

    @property
    def module_path(self):
        return self.imported_name

    @property
    def names(self):
        return self.imported_name

    @property
    def line(self):
        return getattr(self, '_import_line', None)

    __table_args__ = (
        Index("ix_code_imports_source_file", "source_file_id"),
        Index("ix_code_imports_imported_symbol", "imported_symbol_id"),
        Index("ix_code_imports_imported_name", "imported_name"),
    )


# ─── 8. CodeMetrics ─────────────────────────────────────────────────────


class CodeMetrics(Base, TimestampMixin):
    __tablename__ = "code_metrics"

    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_symbols.id", ondelete="SET NULL"),
        nullable=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    loc: Mapped[Optional[int]] = mapped_column(Integer)
    code_lines: Mapped[Optional[int]] = mapped_column(Integer)
    comment_lines: Mapped[Optional[int]] = mapped_column(Integer)
    blank_lines: Mapped[Optional[int]] = mapped_column(Integer)
    cyclomatic_complexity: Mapped[Optional[int]] = mapped_column(Integer)
    cognitive_complexity: Mapped[Optional[int]] = mapped_column(Integer)
    function_length: Mapped[Optional[int]] = mapped_column(Integer)
    class_size: Mapped[Optional[int]] = mapped_column(Integer)
    nesting_depth: Mapped[Optional[int]] = mapped_column(Integer)
    parameter_count: Mapped[Optional[int]] = mapped_column(Integer)
    dependency_count: Mapped[int] = mapped_column(Integer, default=0)
    fan_in: Mapped[int] = mapped_column(Integer, default=0)
    fan_out: Mapped[int] = mapped_column(Integer, default=0)
    maintainability_index: Mapped[Optional[float]] = mapped_column(Float)
    halstead_volume: Mapped[Optional[float]] = mapped_column(Float)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    calculated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # relationships
    file: Mapped["CodeFile"] = relationship(back_populates="metrics")
    symbol: Mapped[Optional["CodeSymbol"]] = relationship(back_populates="metrics")

    @property
    def line_count(self):
        return self.loc

    __table_args__ = (
        Index("ix_code_metrics_file_symbol", "file_id", "symbol_id"),
        Index("ix_code_metrics_repo_id", "repository_id"),
    )


# ─── 9. CodeSmell ───────────────────────────────────────────────────────


class CodeSmell(Base, TimestampMixin):
    __tablename__ = "code_smells"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_symbols.id", ondelete="SET NULL"),
        nullable=True,
    )
    smell_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[Optional[str]] = mapped_column(Text)
    suggested_fix: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    start_line: Mapped[Optional[int]] = mapped_column(Integer)
    end_line: Mapped[Optional[int]] = mapped_column(Integer)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)
    detected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # relationships
    file: Mapped["CodeFile"] = relationship(back_populates="smells")
    symbol: Mapped[Optional["CodeSymbol"]] = relationship(back_populates="smells")

    @property
    def line_start(self):
        return self.start_line

    @property
    def line_end(self):
        return self.end_line

    @property
    def suggestion(self):
        return self.suggested_fix

    @property
    def effort_estimate(self):
        return None

    __table_args__ = (
        Index("ix_code_smells_repo_type", "repository_id", "smell_type"),
        Index("ix_code_smells_file_id", "file_id"),
        Index("ix_code_smells_severity", "severity"),
        Index("ix_code_smells_resolved", "resolved"),
    )


# ─── 10. CodeTest ───────────────────────────────────────────────────────


class CodeTest(Base, TimestampMixin):
    __tablename__ = "code_tests"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_symbols.id", ondelete="SET NULL"),
        nullable=True,
    )
    test_type: Mapped[str] = mapped_column(String(30), nullable=False)
    test_name: Mapped[str] = mapped_column(String(500), nullable=False)
    source_symbol_name: Mapped[Optional[str]] = mapped_column(String(500))
    source_file_path: Mapped[Optional[str]] = mapped_column(String(1000))
    framework: Mapped[Optional[str]] = mapped_column(String(50))
    is_async: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    # relationships
    file: Mapped["CodeFile"] = relationship(back_populates="tests")
    symbol: Mapped[Optional["CodeSymbol"]] = relationship(back_populates="tests")

    __table_args__ = (
        Index("ix_code_tests_repo_id", "repository_id"),
        Index("ix_code_tests_file_id", "file_id"),
        Index("ix_code_tests_source_symbol_name", "source_symbol_name"),
    )


# ─── 11. CodeHistory ────────────────────────────────────────────────────


class CodeHistory(Base, TimestampMixin):
    __tablename__ = "code_history"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_files.id", ondelete="SET NULL"),
        nullable=True,
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    author_email: Mapped[Optional[str]] = mapped_column(String(255))
    author_name: Mapped[Optional[str]] = mapped_column(String(255))
    commit_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    change_type: Mapped[Optional[str]] = mapped_column(String(20))
    lines_added: Mapped[int] = mapped_column(Integer, default=0)
    lines_deleted: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("ix_code_history_repo_path", "repository_id", "file_path"),
        Index("ix_code_history_commit_sha", "commit_sha"),
        Index("ix_code_history_author_email", "author_email"),
        Index("ix_code_history_commit_date", "commit_date"),
    )


# ─── 12. CodeOwnership ──────────────────────────────────────────────────


class CodeOwnership(Base, TimestampMixin):
    __tablename__ = "code_ownership"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_name: Mapped[Optional[str]] = mapped_column(String(255))
    ownership_score: Mapped[float] = mapped_column(Float, default=0.0)
    commits_count: Mapped[int] = mapped_column(Integer, default=0)
    lines_changed: Mapped[int] = mapped_column(Integer, default=0)
    last_commit_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    role: Mapped[Optional[str]] = mapped_column(String(20))

    __table_args__ = (
        Index("ix_code_ownership_repo_path", "repository_id", "file_path"),
        Index("ix_code_ownership_repo_email", "repository_id", "owner_email"),
    )


# ─── 13. CodeChunk ──────────────────────────────────────────────────────


class CodeChunk(Base, TimestampMixin):
    __tablename__ = "code_chunks"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    index_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_indexes.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_symbols.id", ondelete="SET NULL"),
        nullable=True,
    )
    chunk_type: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[Optional[int]] = mapped_column(Integer)
    end_line: Mapped[Optional[int]] = mapped_column(Integer)
    language: Mapped[Optional[str]] = mapped_column(String(50))
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    embedding_id: Mapped[Optional[str]] = mapped_column(String(255))
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100))
    embedding_version: Mapped[Optional[str]] = mapped_column(String(50))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    # relationships
    index: Mapped["CodeIndex"] = relationship(back_populates="chunks")
    file: Mapped["CodeFile"] = relationship(back_populates="chunks")
    symbol: Mapped[Optional["CodeSymbol"]] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_code_chunks_repo_type", "repository_id", "chunk_type"),
        Index("ix_code_chunks_file_id", "file_id"),
        Index("ix_code_chunks_embedding_id", "embedding_id"),
    )


# ─── 14. CodeIndexJob ───────────────────────────────────────────────────


class CodeIndexJob(Base, TimestampMixin):
    __tablename__ = "code_index_jobs"

    index_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_indexes.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=JobStatus.PENDING.value
    )
    file_ids: Mapped[Optional[dict]] = mapped_column(JSONB)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # relationships
    index: Mapped["CodeIndex"] = relationship(back_populates="jobs")

    __table_args__ = (
        Index("ix_code_index_jobs_index_status", "index_id", "status"),
        Index("ix_code_index_jobs_status_priority", "status", "priority"),
    )
