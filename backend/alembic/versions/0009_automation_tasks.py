"""Alembic migration: Autonomous Software-Engineering layer (Volume 45).

Revision ID: 0009_automation_tasks
Revises: 0008_marketplace
"""

from alembic import op
from sqlalchemy import inspect

from app.core.database import Base
from app.automation import models as _auto_models  # noqa: F401

revision = "0009_automation_tasks"
down_revision = "0008_marketplace"
branch_labels = None
depends_on = None

AUTOMATION_TABLES = [
    "automation_tasks",
    "automation_plans",
    "automation_steps",
    "automation_patches",
    "automation_test_runs",
    "automation_reviews",
    "automation_approvals",
    "automation_deployments",
    "automation_budgets",
    "automation_checkpoints",
    "automation_workflow_templates",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    tables = [
        Base.metadata.tables[t]
        for t in AUTOMATION_TABLES
        if t in Base.metadata.tables
    ]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    for t in AUTOMATION_TABLES:
        if t in existing:
            op.drop_table(t)
