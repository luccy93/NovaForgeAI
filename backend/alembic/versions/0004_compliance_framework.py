"""SRE (Volume 35) - compliance framework schema migration.

Revision ID: 0004_compliance_framework
Revises: 0003_sre
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_compliance_framework"
down_revision = "0003_sre"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── compliance_frameworks ──────────────────────────────────────────
    op.create_table(
        "compliance_frameworks",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.description("Name of the compliance framework (e.g. SOC 2, ISO 27001, GDPR)"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), server_default="planned", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("controls_count", sa.Integer(), server_default="0"),
        sa.Column("passed_assessments", sa.Integer(), server_default="0"),
        sa.Column("failed_assessments", sa.Integer(), server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compliance_frameworks_organization", "compliance_frameworks", ["organization_id"])
    op.create_index("ix_compliance_frameworks_name", "compliance_frameworks", ["name"], unique=True)

    # ── compliance_controls ────────────────────────────────────────────
    op.create_table(
        "compliance_controls",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("framework_id", sa.Uuid(), sa.ForeignKey("compliance_frameworks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("control_id", sa.String(64), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), server_default="not_implemented", nullable=False),
        sa.Column("implementation", sa.Text(), nullable=True),
        sa.Column("evidence_requirements", sa.Text(), nullable=True),
        sa.Column("frequency", sa.String(32), server_default="annual", nullable=False),
        sa.Column("risk", sa.String(32), server_default="medium", nullable=False),
        sa.Column("owner", sa.String(128), nullable=True),
        sa.Column("last_review", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_review", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exception_reason", sa.Text(), nullable=True),
        sa.Column("exception_approved_by", sa.String(128), nullable=True),
        sa.Column("exception_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compensating_controls", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_compliance_controls_framework", "compliance_controls", ["framework_id"])
    op.create_index("ix_compliance_controls_org_status", "compliance_controls", ["org_id", "status"])
    op.create_index("ix_compliance_controls_org_framework", "compliance_controls", ["org_id", "framework_id"])

    # ── compliance_control_mappings ────────────────────────────────────
    op.create_table(
        "compliance_control_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("source_control_id", sa.Uuid(), sa.ForeignKey("compliance_controls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_framework", sa.String(32), nullable=False),
        sa.Column("mapped_control_id", sa.String(64), nullable=False),
        sa.Column("mapping_strength", sa.String(32), server_default="strong", nullable=False),
        sa.Column("mapping_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mappings_source_control", "compliance_control_mappings", ["source_control_id"])

    # ── compliance_evidence ────────────────────────────────────────────
    op.create_table(
        "compliance_evidence",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("control_id", sa.Uuid(), sa.ForeignKey("compliance_controls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),  # e.g. audit_log, scan, policy, incident
        sa.Column("type", sa.String(32), nullable=False),  # e.g. document, log, configuration, test_result, scan_result
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collector", sa.String(128), nullable=True),  # e.g. automated, manual
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("hash_sha256", sa.String(64), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("owner", sa.String(128), nullable=True),
        sa.Column("verification_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_control", "compliance_evidence", ["control_id"])
    op.create_index("ix_evidence_timestamp", "compliance_evidence", ["timestamp"])

    # ── compliance_tests ───────────────────────────────────────────────
    op.create_table(
        "compliance_tests",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("control_id", sa.Uuid(), sa.ForeignKey("compliance_controls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("test_name", sa.String(128), nullable=False),
        sa.Column("test_type", sa.String(32), nullable=True),  # e.g. automated, manual, integration
        sa.Column("result", sa.String(32), nullable=True),  # e.g. pass, fail, warning, info
        sa.Column("evidence_id", sa.Uuid(), sa.ForeignKey("compliance_evidence.id", ondelete="SET NULL"), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("failed_reason", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_by", sa.String(128), nullable=True),
        sa.Column("timestamp_completed", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tests_control", "compliance_tests", ["control_id"])

    # ── compliance_policies ────────────────────────────────────────────
    op.create_table(
        "compliance_policies",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("framework_id", sa.Uuid(), sa.ForeignKey("compliance_frameworks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("policy_type", sa.String(32), nullable=False),  # e.g. security, privacy, data_retention, ai_usage
        sa.Column("version", sa.String(32), server_default="1.0.0", nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),  # draft, active, deprecated
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expiration_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner", sa.String(128), nullable=True),
        sa.Column("approval_status", sa.String(32), server_default="pending", nullable=False),  # pending, approved, rejected
        sa.Column("approval_by", sa.String(128), nullable=True),
        sa.Column("approval_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("constraints", sa.Text(), nullable=True),
        sa.Column("actions", sa.Text(), nullable=True),
        sa.Column("tags", sa.String(256), nullable=True),  # comma-separated
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policies_framework", "compliance_policies", ["framework_id"])
    op.create_index("ix_policies_org_status", "compliance_policies", ["org_id", "status"])

    # ── compliance_exceptions ──────────────────────────────────────────
    op.create_table(
        "compliance_exceptions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("control_id", sa.Uuid(), sa.ForeignKey("compliance_controls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("risk", sa.String(32), nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("compensating_controls", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exceptions_control", "compliance_exceptions", ["control_id"])

    # ── compliance_risks ────────────────────────────────────────────────
    op.create_table(
        "compliance_risks",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(32), nullable=True),  # e.g. security, privacy, operational, financial
        sa.Column("likelihood", sa.String(32), server_default="medium", nullable=False),
        sa.Column("impact", sa.String(32), server_default="medium", nullable=False),
        sa.Column("risk_score", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("affected_assets", sa.Text(), nullable=True),
        sa.Column("mitigation_plan", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),  # active, closed, transferred
        sa.Column("owner", sa.String(128), nullable=True),
        sa.Column("last_review", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_review", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risks_org", "compliance_risks", ["org_id"])
    op.create_index("ix_risks_status", "compliance_risks", ["status"])

    # ── compliance_vendors ──────────────────────────────────────────────
    op.create_table(
        "compliance_vendors",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("service", sa.String(128), nullable=True),  # e.g. aws, azure, github, sendgrid
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column("criticality", sa.String(32), server_default="medium", nullable=False),
        sa.Column("security_status", sa.String(32), server_default="pending", nullable=False),  # pending, approved, declined
        sa.Column("contract_status", sa.String(32), server_default="active", nullable=False),
        sa.Column("contract_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contract_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_processed", sa.Text(), nullable=True),
        sa.Column("risk_assessment", sa.Text(), nullable=True),
        sa.Column("evidence_reference", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vendors_org", "compliance_vendors", ["org_id"])
    op.create_index("ix_vendors_name", "compliance_vendors", ["name"], unique=True)

    # ── compliance_data_assets ──────────────────────────────────────────
    op.create_table(
        "compliance_data_assets",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(32), nullable=True),  # e.g. user_data, financial, health, pii, code, configuration, logs, metrics, documents, ai_model, prompt, audit
        sa.Column("classification", sa.String(32), nullable=True),  # public, internal, confidential, restricted, highly_restricted
        sa.Column("location", sa.String(256), nullable=True),  # e.g. postgres, redis, qdrant, neo4j, object_storage, logs, backups, repositories, ai_traces, evaluation_data
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("retention_action", sa.String(32), server_default="delete", nullable=False),  # delete, archive, anonymize, export, transfer
        sa.Column("processors", sa.Text(), nullable=True),  # comma-separated list
        sa.Column("access_policy", sa.Text(), nullable=True),
        sa.Column("deletion_policy", sa.Text(), nullable=True),
        sa.Column("tags", sa.String(256), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dataassets_org", "compliance_data_assets", ["org_id"])
    op.create_index("ix_dataassets_classification", "compliance_data_assets", ["classification"])
    op.create_index("ix_dataassets_location", "compliance_data_assets", ["location"])

    # ── compliance_retention_policies ────────────────────────────────────
    op.create_table(
        "compliance_retention_policies",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("classification", sa.String(32), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(32), server_default="delete", nullable=False),  # delete, archive, anonymize, export, transfer
        sa.Column("exempt_assets", sa.Text(), nullable=True),  # comma-separated asset IDs
        sa.Column("enabled", sa.Boolean(), server_default=True, nullable=False),
        sa.Column("jurisdiction", sa.String(64), nullable=True),  # e.g. us, eu, apac
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_retention_policies_org", "compliance_retention_policies", ["org_id"])

    # ── compliance_deletion_requests ─────────────────────────────────────
    op.create_table(
        "compliance_deletion_requests",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("compliance_data_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requester", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),  # pending, approved, completed, rejected
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deletion_requests_org", "compliance_deletion_requests", ["org_id"])
    op.create_index("ix_deletion_requests_asset", "compliance_deletion_requests", ["asset_id"])

    # ── compliance_exports ──────────────────────────────────────────────
    op.create_table(
        "compliance_exports",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("export_type", sa.String(64), nullable=False),  # e.g. user_data, organization_data, audit_records, compliance_evidence
        sa.Column("format", sa.String(32), nullable=True),  # e.g. json, csv, xml, pdf
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),  # pending, processing, completed, failed
        sa.Column("filter_criteria", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(128), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("download_url", sa.Text(), nullable=True),
        sa.Column("audit_log_id", sa.Uuid(), sa.ForeignKey("audit_logs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exports_org", "compliance_exports", ["org_id"])
    op.create_index("ix_exports_status", "compliance_exports", ["status"])

    # ── compliance_access_reviews ────────────────────────────────────────
    op.create_table(
        "compliance_access_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("review_type", sa.String(32), nullable=False),  # e.g. users, roles, api_keys, service_accounts, oauth_connections, repositories, privileged_permissions
        sa.Column("scope", sa.String(128), nullable=True),
        sa.Column("reviewers", sa.String(256), nullable=True),  # comma-separated list of reviewer emails/IDs
        sa.Column("reviewers_status", sa.String(32), server_default="pending", nullable=False),  # pending, approved, revoked, expired
        sa.Column("review_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewers_completed", sa.Integer(), server_default="0"),
        sa.Column("reviewers_total", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),  # pending, approved, revoked, expired
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("actions_required", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accessreviews_org", "compliance_access_reviews", ["org_id"])
    op.create_index("ix_accessreviews_status", "compliance_access_reviews", ["status"])

    # ── compliance_legal_holds ──────────────────────────────────────────
    op.create_table(
        "compliance_legal_holds",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("hold_name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hold_scope", sa.Text(), nullable=True),  # e.g. all_data, specific_tables, specific_assets
        sa.Column("affected_assets", sa.Text(), nullable=True),  # comma-separated asset IDs
        sa.Column("hold_reason", sa.Text(), nullable=True),
        sa.Column("held_by", sa.String(128), nullable=True),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("holds_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),  # active, released, expired
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_legalholds_org", "compliance_legal_holds", ["org_id"])
    op.create_index("ix_legalholds_status", "compliance_legal_holds", ["status"])


def downgrade() -> None:
    # Drop in reverse order to maintain foreign key integrity
    op.drop_table("compliance_legal_holds")
    op.drop_table("compliance_access_reviews")
    op.drop_table("compliance_exports")
    op.drop_table("compliance_deletion_requests")
    op.drop_table("compliance_retention_policies")
    op.drop_table("compliance_data_assets")
    op.drop_table("compliance_vendors")
    op.drop_table("compliance_risks")
    op.drop_table("compliance_exceptions")
    op.drop_table("compliance_policies")
    op.drop_table("compliance_tests")
    op.drop_table("compliance_evidence")
    op.drop_table("compliance_control_mappings")
    op.drop_table("compliance_controls")
    op.drop_table("compliance_frameworks")