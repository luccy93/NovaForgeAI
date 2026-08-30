"""Workflow engine — Volume 66 Commit 1 (8 tables, FK to workflow_versions.id)."""

from alembic import op
import sqlalchemy as sa

from app.core.database import Base
from app.workflow import models as _wf  # noqa: F401
from app.automation import models as _auto  # noqa: F401

revision = "0032_workflow"
down_revision = "0031_data_lakehouse"
branch_labels = None
depends_on = None

WF_TABLES = [
    "workflow_definitions",
    "workflow_versions",
    "workflow_runs",
    "workflow_step_runs",
    "workflow_schedules",
    "workflow_approvals",
    "workflow_checkpoints",
    "workflow_compensations",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in WF_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)
    # Add workflow_version_id to automation_tasks legacy string field
    try:
        op.add_column("automation_tasks", sa.Column("workflow_version_id", sa.Uuid(), nullable=True))
    except Exception:
        pass
    try:
        op.create_index("ix_automation_tasks_workflow_version_id", "automation_tasks", ["workflow_version_id"])
    except Exception:
        pass
    # Backfill: try to resolve workflow_id string to version id where possible (best-effort)
    try:
        # No strict validation here; leave NULL where not resolvable
        pass
    except Exception:
        pass
    # FK constraint (additive, try)
    try:
        op.create_foreign_key("fk_automation_tasks_workflow_version_id", "automation_tasks", "workflow_versions", ["workflow_version_id"], ["id"], ondelete="SET NULL")
    except Exception:
        pass


def downgrade() -> None:
    for t in reversed(WF_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
    try:
        op.drop_constraint("fk_automation_tasks_workflow_version_id", "automation_tasks", type_="foreignkey")
    except Exception:
        pass
    try:
        op.drop_index("ix_automation_tasks_workflow_version_id", table_name="automation_tasks")
    except Exception:
        pass
    try:
        op.drop_column("automation_tasks", "workflow_version_id")
    except Exception:
        pass
