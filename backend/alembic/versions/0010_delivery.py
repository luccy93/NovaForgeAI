"""Alembic migration: Software Delivery Platform (Volume 46).

Revision ID: 0010_delivery
Revises: 0009_automation_tasks
"""

from alembic import op
from sqlalchemy import inspect

from app.core.database import Base
from app.delivery import models as _delivery_models  # noqa: F401

revision = "0010_delivery"
down_revision = "0009_automation_tasks"
branch_labels = None
depends_on = None

DELIVERY_TABLES = [
    "delivery_pipelines",
    "delivery_pipeline_runs",
    "delivery_jobs",
    "delivery_runners",
    "delivery_artifacts",
    "delivery_environments",
    "delivery_deployments",
    "delivery_releases",
    "delivery_rollouts",
    "delivery_rollbacks",
    "delivery_preview_environments",
    "delivery_approvals",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    tables = [
        Base.metadata.tables[t]
        for t in DELIVERY_TABLES
        if t in Base.metadata.tables
    ]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    for t in DELIVERY_TABLES:
        if t in existing:
            op.drop_table(t)
