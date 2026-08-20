"""Alembic migration: Quality Engine tables (Volume 48)

Revision ID: 0012
Revises: 0011_security_platform
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text

revision = "0012_quality_engine"
down_revision = "0011_security_platform"
branch_labels = None
depends_on = None

from app.core.database import Base
from app.quality import models as quality_models

QUALITY_TABLES = [
    "quality_reviews",
    "quality_review_runs",
    "quality_findings",
    "quality_baselines",
    "quality_gates",
    "quality_gate_evaluations",
    "quality_review_feedback",
    "quality_test_analysis",
    "quality_review_versions",
    "quality_remediations",
    "quality_metrics_history",
    "quality_duplication_groups",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in QUALITY_TABLES if name in Base.metadata.tables]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for name in reversed(QUALITY_TABLES):
        op.drop_table(name)
