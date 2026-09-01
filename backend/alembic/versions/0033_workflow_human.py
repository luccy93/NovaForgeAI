"""Workflow human tasks, business, templates — Volume 66 Commit 2 (3 tables)."""

from alembic import op

from app.core.database import Base
from app.workflow import human_tasks as _ht  # noqa: F401
from app.workflow import business as _biz  # noqa: F401
from app.workflow import templates as _tmpl  # noqa: F401

revision = "0033_workflow_human"
down_revision = "0032_workflow"
branch_labels = None
depends_on = None

WF_HUMAN_TABLES = [
    "workflow_human_tasks",
    "workflow_business_processes",
    "workflow_templates",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in WF_HUMAN_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in reversed(WF_HUMAN_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
