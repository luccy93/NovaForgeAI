"""Code Intelligence (Volume 38) - schema migration.

Revision ID: 0006_code_intelligence
Revises: 0005_ai_governance
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_code_intelligence"
down_revision = "0005_ai_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── code_indexes ────────────────────────────────────────────────────────
    op.create_table(
        "code_indexes",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("index_type", sa.String(64), nullable=False),  # ast, symbol, call_graph, dependency, semantic
        sa.Column("language", sa.String(32), nullable=True),  # python, javascript, typescript, go, rust, java, c, cpp
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),  # pending, indexing, ready, error, stale
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("repo_url", sa.Text(), nullable=True),
        sa.Column("repo_branch", sa.String(256), nullable=True),
        sa.Column("repo_commit", sa.String(64), nullable=True),
        sa.Column("root_path", sa.Text(), nullable=True),
        sa.Column("file_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("symbol_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("index_size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("index_duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("config", sa.Text(), nullable=True),  # JSON
        sa.Column("tags", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_indexes_org", "code_indexes", ["org_id"])
    op.create_index("ix_code_indexes_type", "code_indexes", ["index_type"])
    op.create_index("ix_code_indexes_status", "code_indexes", ["status"])
    op.create_index("ix_code_indexes_language", "code_indexes", ["language"])

    # ── code_index_versions ────────────────────────────────────────────────
    op.create_table(
        "code_index_versions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),  # pending, indexing, ready, error
        sa.Column("repo_commit", sa.String(64), nullable=True),
        sa.Column("repo_branch", sa.String(256), nullable=True),
        sa.Column("file_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("symbol_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("index_size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("diff_summary", sa.Text(), nullable=True),  # JSON
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_index_versions_index", "code_index_versions", ["index_id"])
    op.create_index("ix_code_index_versions_version", "code_index_versions", ["index_id", "version"])

    # ── code_files ──────────────────────────────────────────────────────────
    op.create_table(
        "code_files",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(256), nullable=False),
        sa.Column("file_ext", sa.String(16), nullable=True),
        sa.Column("language", sa.String(32), nullable=True),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("line_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("code_line_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("comment_line_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("blank_line_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("complexity_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("hash_sha256", sa.String(64), nullable=True),
        sa.Column("last_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_modified_by", sa.String(128), nullable=True),
        sa.Column("is_test_file", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("is_generated", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("is_dependency", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_files_index", "code_files", ["index_id"])
    op.create_index("ix_code_files_path", "code_files", ["index_id", "file_path"])
    op.create_index("ix_code_files_language", "code_files", ["language"])
    op.create_index("ix_code_files_ext", "code_files", ["file_ext"])

    # ── code_symbols ────────────────────────────────────────────────────────
    op.create_table(
        "code_symbols",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("code_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=True),
        sa.Column("symbol_type", sa.String(32), nullable=False),  # function, method, class, module, variable, constant, enum, interface, type, parameter, attribute, property
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("docstring", sa.Text(), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("start_col", sa.Integer(), nullable=True),
        sa.Column("end_col", sa.Integer(), nullable=True),
        sa.Column("complexity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("parameters", sa.Text(), nullable=True),  # JSON
        sa.Column("return_type", sa.String(256), nullable=True),
        sa.Column("parent_symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="SET NULL"), nullable=True),
        sa.Column("visibility", sa.String(16), server_default="public", nullable=False),  # public, private, protected, internal
        sa.Column("is_async", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("is_abstract", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("is_static", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("decorators", sa.Text(), nullable=True),  # JSON array
        sa.Column("annotations", sa.Text(), nullable=True),  # JSON
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_symbols_index", "code_symbols", ["index_id"])
    op.create_index("ix_code_symbols_file", "code_symbols", ["file_id"])
    op.create_index("ix_code_symbols_type", "code_symbols", ["symbol_type"])
    op.create_index("ix_code_symbols_name", "code_symbols", ["name"])
    op.create_index("ix_code_symbols_parent", "code_symbols", ["parent_symbol_id"])
    op.create_index("ix_code_symbols_qualified", "code_symbols", ["qualified_name"])

    # ── code_references ─────────────────────────────────────────────────────
    op.create_table(
        "code_references",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_file_id", sa.Uuid(), sa.ForeignKey("code_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_file_id", sa.Uuid(), sa.ForeignKey("code_files.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="CASCADE"), nullable=True),
        sa.Column("target_symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reference_type", sa.String(32), nullable=False),  # import, include, require, extend, implement, type_ref, annotation
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("column_number", sa.Integer(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("resolved", sa.Boolean(), server_default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_references_index", "code_references", ["index_id"])
    op.create_index("ix_code_references_source_file", "code_references", ["source_file_id"])
    op.create_index("ix_code_references_target_file", "code_references", ["target_file_id"])
    op.create_index("ix_code_references_type", "code_references", ["reference_type"])
    op.create_index("ix_code_references_source_symbol", "code_references", ["source_symbol_id"])

    # ── code_calls ──────────────────────────────────────────────────────────
    op.create_table(
        "code_calls",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("caller_symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="CASCADE"), nullable=False),
        sa.Column("callee_symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="SET NULL"), nullable=True),
        sa.Column("callee_name", sa.Text(), nullable=True),
        sa.Column("call_type", sa.String(32), server_default="direct", nullable=False),  # direct, dynamic, callback, lambda, decorator, inheritance
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("column_number", sa.Integer(), nullable=True),
        sa.Column("is_conditional", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("is_awaited", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("arguments", sa.Text(), nullable=True),  # JSON
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_calls_index", "code_calls", ["index_id"])
    op.create_index("ix_code_calls_caller", "code_calls", ["caller_symbol_id"])
    op.create_index("ix_code_calls_callee", "code_calls", ["callee_symbol_id"])
    op.create_index("ix_code_calls_type", "code_calls", ["call_type"])

    # ── code_imports ────────────────────────────────────────────────────────
    op.create_table(
        "code_imports",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("code_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_path", sa.Text(), nullable=False),
        sa.Column("import_type", sa.String(32), nullable=False),  # absolute, relative, wildcard, dynamic, lazy
        sa.Column("imported_names", sa.Text(), nullable=True),  # JSON array
        sa.Column("alias", sa.String(256), nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=True),
        sa.Column("is_unused", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("resolved", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("target_file_id", sa.Uuid(), sa.ForeignKey("code_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_external", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("package_name", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_imports_index", "code_imports", ["index_id"])
    op.create_index("ix_code_imports_file", "code_imports", ["file_id"])
    op.create_index("ix_code_imports_path", "code_imports", ["import_path"])
    op.create_index("ix_code_imports_target", "code_imports", ["target_file_id"])

    # ── code_metrics ────────────────────────────────────────────────────────
    op.create_table(
        "code_metrics",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("code_files.id", ondelete="CASCADE"), nullable=True),
        sa.Column("symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="CASCADE"), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("metric_type", sa.String(64), nullable=False),  # cyclomatic, cognitive, halstead_volume, maintainability_index, lines_of_code, comment_ratio, duplication_ratio, coupling, cohesion
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("grade", sa.String(8), nullable=True),  # A, B, C, D, F
        sa.Column("details", sa.Text(), nullable=True),  # JSON
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tool_version", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_metrics_index", "code_metrics", ["index_id"])
    op.create_index("ix_code_metrics_file", "code_metrics", ["file_id"])
    op.create_index("ix_code_metrics_symbol", "code_metrics", ["symbol_id"])
    op.create_index("ix_code_metrics_type", "code_metrics", ["metric_type"])
    op.create_index("ix_code_metrics_version", "code_metrics", ["index_id", "version"])

    # ── code_smells ─────────────────────────────────────────────────────────
    op.create_table(
        "code_smells",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("code_files.id", ondelete="CASCADE"), nullable=True),
        sa.Column("symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("smell_type", sa.String(64), nullable=False),  # long_method, large_class, god_class, feature_envy, data_clump, switch_statements, long_parameter_list, dead_code, duplicated_code, deep_nesting, complex_method, shotgun_surgery, feature_couple, message_chains
        sa.Column("severity", sa.String(16), server_default="low", nullable=False),  # info, low, medium, high, critical
        sa.Column("line_start", sa.Integer(), nullable=True),
        sa.Column("line_end", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("status", sa.String(32), server_default="open", nullable=False),  # open, acknowledged, fixing, fixed, wont_fix, suppressed
        sa.Column("suppressed", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("suppress_reason", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_smells_index", "code_smells", ["index_id"])
    op.create_index("ix_code_smells_file", "code_smells", ["file_id"])
    op.create_index("ix_code_smells_symbol", "code_smells", ["symbol_id"])
    op.create_index("ix_code_smells_type", "code_smells", ["smell_type"])
    op.create_index("ix_code_smells_severity", "code_smells", ["severity"])
    op.create_index("ix_code_smells_status", "code_smells", ["status"])

    # ── code_tests ──────────────────────────────────────────────────────────
    op.create_table(
        "code_tests",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("code_files.id", ondelete="CASCADE"), nullable=True),
        sa.Column("test_symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("test_name", sa.String(512), nullable=False),
        sa.Column("test_type", sa.String(32), nullable=False),  # unit, integration, functional, performance, smoke, regression
        sa.Column("test_file", sa.Text(), nullable=True),
        sa.Column("test_class", sa.String(256), nullable=True),
        sa.Column("test_method", sa.String(256), nullable=True),
        sa.Column("covered_symbols", sa.Text(), nullable=True),  # JSON array of symbol IDs
        sa.Column("covers_file_id", sa.Uuid(), sa.ForeignKey("code_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("framework", sa.String(64), nullable=True),  # pytest, unittest, jest, mocha, go_test, rspec
        sa.Column("markers", sa.Text(), nullable=True),  # JSON array
        sa.Column("estimated_duration_ms", sa.Integer(), nullable=True),
        sa.Column("assertion_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_tests_index", "code_tests", ["index_id"])
    op.create_index("ix_code_tests_file", "code_tests", ["file_id"])
    op.create_index("ix_code_tests_symbol", "code_tests", ["test_symbol_id"])
    op.create_index("ix_code_tests_type", "code_tests", ["test_type"])
    op.create_index("ix_code_tests_framework", "code_tests", ["framework"])

    # ── code_history ────────────────────────────────────────────────────────
    op.create_table(
        "code_history",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("code_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),  # file_added, file_modified, file_deleted, symbol_added, symbol_modified, symbol_deleted, refactor_detected, import_changed, test_added, test_removed, smell_detected, smell_resolved, metric_change
        sa.Column("commit_sha", sa.String(64), nullable=True),
        sa.Column("commit_message", sa.Text(), nullable=True),
        sa.Column("commit_author", sa.String(128), nullable=True),
        sa.Column("commit_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("branch", sa.String(256), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),  # JSON
        sa.Column("diff_stats", sa.Text(), nullable=True),  # JSON: additions, deletions
        sa.Column("risk_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("churn_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_history_index", "code_history", ["index_id"])
    op.create_index("ix_code_history_file", "code_history", ["file_id"])
    op.create_index("ix_code_history_symbol", "code_history", ["symbol_id"])
    op.create_index("ix_code_history_event", "code_history", ["event_type"])
    op.create_index("ix_code_history_commit", "code_history", ["commit_sha"])
    op.create_index("ix_code_history_author", "code_history", ["commit_author"])

    # ── code_ownership ──────────────────────────────────────────────────────
    op.create_table(
        "code_ownership",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("code_files.id", ondelete="CASCADE"), nullable=True),
        sa.Column("symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner", sa.String(128), nullable=False),
        sa.Column("ownership_type", sa.String(32), server_default="primary", nullable=False),  # primary, secondary, team
        sa.Column("contribution_percentage", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("commit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_commit_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_commit_sha", sa.String(64), nullable=True),
        sa.Column("knowledge_areas", sa.Text(), nullable=True),  # JSON array of topics/domains
        sa.Column("responsibilities", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),  # active, transitioning, inactive
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_ownership_index", "code_ownership", ["index_id"])
    op.create_index("ix_code_ownership_file", "code_ownership", ["file_id"])
    op.create_index("ix_code_ownership_symbol", "code_ownership", ["symbol_id"])
    op.create_index("ix_code_ownership_owner", "code_ownership", ["owner"])
    op.create_index("ix_code_ownership_type", "code_ownership", ["ownership_type"])

    # ── code_chunks ─────────────────────────────────────────────────────────
    op.create_table(
        "code_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.Uuid(), sa.ForeignKey("code_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_type", sa.String(32), nullable=False),  # file, function, class, module_section, comment_block
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding_id", sa.String(256), nullable=True),  # reference to vector store
        sa.Column("metadata", sa.Text(), nullable=True),  # JSON
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_chunks_index", "code_chunks", ["index_id"])
    op.create_index("ix_code_chunks_file", "code_chunks", ["file_id"])
    op.create_index("ix_code_chunks_symbol", "code_chunks", ["symbol_id"])
    op.create_index("ix_code_chunks_type", "code_chunks", ["chunk_type"])
    op.create_index("ix_code_chunks_hash", "code_chunks", ["content_hash"])

    # ── code_index_jobs ─────────────────────────────────────────────────────
    op.create_table(
        "code_index_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("index_id", sa.Uuid(), sa.ForeignKey("code_indexes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_type", sa.String(32), nullable=False),  # full_index, incremental, reindex, delete
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),  # pending, queued, running, completed, failed, cancelled
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("triggered_by", sa.String(128), nullable=True),
        sa.Column("trigger_reason", sa.String(64), nullable=True),  # manual, scheduled, commit_detected, config_change, force
        sa.Column("repo_commit", sa.String(64), nullable=True),
        sa.Column("repo_branch", sa.String(256), nullable=True),
        sa.Column("files_processed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("files_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("symbols_extracted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("errors_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("config", sa.Text(), nullable=True),  # JSON
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_code_index_jobs_index", "code_index_jobs", ["index_id"])
    op.create_index("ix_code_index_jobs_status", "code_index_jobs", ["status"])
    op.create_index("ix_code_index_jobs_type", "code_index_jobs", ["job_type"])
    op.create_index("ix_code_index_jobs_priority", "code_index_jobs", ["priority"])


def downgrade() -> None:
    op.drop_table("code_index_jobs")
    op.drop_table("code_chunks")
    op.drop_table("code_ownership")
    op.drop_table("code_history")
    op.drop_table("code_tests")
    op.drop_table("code_smells")
    op.drop_table("code_metrics")
    op.drop_table("code_imports")
    op.drop_table("code_calls")
    op.drop_table("code_references")
    op.drop_table("code_symbols")
    op.drop_table("code_files")
    op.drop_table("code_index_versions")
    op.drop_table("code_indexes")
