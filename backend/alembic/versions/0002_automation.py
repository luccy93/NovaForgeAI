"""Automation, RPA & Intelligent Automation (Volume 33) - schema migration.

Revision ID: 0002_automation
Revises: 0001_multimodal
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_automation"
down_revision = "0001_multimodal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else "postgresql"
    json_type = JSONB if dialect == "postgresql" else sa.JSON

    # -------------------------------------------------------------- workflows
    op.create_table(
        "automation_workflows",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workflow_id", sa.String(96), nullable=False, unique=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, default=""),
        sa.Column("version", sa.Integer, nullable=False, default=1),
        sa.Column("status", sa.String(24), nullable=False, default="draft", index=True),
        sa.Column("trigger", json_type, default=dict),
        sa.Column("steps", json_type, default=list),
        sa.Column("policies", json_type, default=dict),
        sa.Column("created_by", sa.String(128), default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_automation_workflows_org_status",
                    "automation_workflows", ["organization_id", "status"])

    # ------------------------------------------------------------- versions
    op.create_table(
        "automation_workflow_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version_id", sa.String(64), nullable=False, unique=True),
        sa.Column("workflow_id", sa.String(96), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(24), default="draft"),
        sa.Column("notes", sa.Text, default=""),
        sa.Column("created_by", sa.String(128), default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("spec", json_type, default=dict),
    )

    # ----------------------------------------------------------- executions
    op.create_table(
        "automation_executions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("execution_id", sa.String(96), nullable=False, unique=True),
        sa.Column("workflow_id", sa.String(96), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("status", sa.String(24), nullable=False, default="queued", index=True),
        sa.Column("version", sa.Integer, default=1),
        sa.Column("trigger", json_type, default=dict),
        sa.Column("inputs", json_type, default=dict),
        sa.Column("steps", json_type, default=dict),
        sa.Column("output", json_type, default=dict),
        sa.Column("error", sa.Text, default=""),
        sa.Column("total_ms", sa.Integer, default=0),
        sa.Column("attempts", sa.Integer, default=1),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_automation_executions_org_status",
                    "automation_executions", ["organization_id", "status"])

    # ------------------------------------------------------------ checkpoints
    op.create_table(
        "automation_checkpoints",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("execution_id", sa.String(96), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("step_id", sa.String(96), nullable=False),
        sa.Column("sequence", sa.Integer, default=0),
        sa.Column("outputs", json_type, default=dict),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------- approvals
    op.create_table(
        "automation_approvals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workflow_id", sa.String(96), nullable=False, index=True),
        sa.Column("step_id", sa.String(96), nullable=False),
        sa.Column("execution_id", sa.String(96), default=""),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("decision", sa.String(24), nullable=False, default="pending", index=True),
        sa.Column("actor", sa.String(128), default=""),
        sa.Column("actor_type", sa.String(24), default="human"),
        sa.Column("reason", sa.Text, default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ------------------------------------------------------------ compensations
    op.create_table(
        "automation_compensations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("execution_id", sa.String(96), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("step_id", sa.String(96), nullable=False),
        sa.Column("compensating_tool", sa.String(96), default=""),
        sa.Column("inputs", json_type, default=dict),
        sa.Column("status", sa.String(24), default="queued"),
        sa.Column("error", sa.Text, default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --------------------------------------------------------------- triggers
    op.create_table(
        "automation_triggers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("workflow_id", sa.String(96), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("trigger_type", sa.String(24), nullable=False),
        sa.Column("definition", json_type, default=dict),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------- webhooks
    op.create_table(
        "automation_webhooks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("path", sa.String(255), nullable=False, unique=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("secret_hash", sa.String(128), default=""),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -------------------------------------------------------------- artifacts
    op.create_table(
        "automation_artifacts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("artifact_id", sa.String(96), nullable=False, unique=True),
        sa.Column("workflow_id", sa.String(96), nullable=False, index=True),
        sa.Column("execution_id", sa.String(96), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("name", sa.String(255), default=""),
        sa.Column("content_type", sa.String(64), default="application/json"),
        sa.Column("size_bytes", sa.Integer, default=0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ----------------------------------------------------------------- costs
    op.create_table(
        "automation_costs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("execution_id", sa.String(96), nullable=False, index=True),
        sa.Column("step_id", sa.String(96), nullable=False),
        sa.Column("workflow_id", sa.String(96), default=""),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("cost_usd", sa.Numeric(14, 6), nullable=False, default=0),
        sa.Column("currency", sa.String(8), default="USD"),
        sa.Column("estimated", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -------------------------------------------------------------- knowledge
    op.create_table(
        "automation_knowledge",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("knowledge_id", sa.String(96), nullable=False, unique=True),
        sa.Column("workflow_id", sa.String(96), default="", index=True),
        sa.Column("step_id", sa.String(96), default=""),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("title", sa.String(255), default=""),
        sa.Column("body", sa.Text, default=""),
        sa.Column("tags", json_type, default=list),
        sa.Column("source", sa.String(24), default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ---------------------------------------------------------- marketplace
    op.create_table(
        "automation_marketplace",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("entry_id", sa.String(96), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, default=""),
        sa.Column("workflow", json_type, default=dict),
        sa.Column("publisher", sa.String(128), default=""),
        sa.Column("version", sa.Integer, default=1),
        sa.Column("installed", sa.Integer, default=0),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --------------------------------------------------------------- events
    op.create_table(
        "automation_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("event_id", sa.String(96), nullable=False, unique=True),
        sa.Column("topic", sa.String(96), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), default="", index=True),
        sa.Column("payload", json_type, default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in ("automation_events", "automation_marketplace",
                  "automation_knowledge", "automation_costs",
                  "automation_artifacts", "automation_webhooks",
                  "automation_triggers", "automation_compensations",
                  "automation_approvals", "automation_checkpoints",
                  "automation_executions", "automation_workflow_versions",
                  "automation_workflows"):
        op.drop_table(table) if _table_exists(table) else None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind) if bind is not None else None
    if inspector is None:
        return True  # best effort on non-bound migration runs
    return name in inspector.get_table_names()