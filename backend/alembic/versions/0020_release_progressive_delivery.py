"""Release management & progressive delivery — Volume 56 additive-only.

Revision ID: 0020_release_progressive_delivery
Revises: 0019_marketplace_ecosystem
"""

from alembic import op
from sqlalchemy import inspect

from app.core.database import Base
from app.release import models as _rel_models  # noqa: F401 — registers tables

revision = "0020_release_progressive_delivery"
down_revision = "0019_marketplace_ecosystem"
branch_labels = None
depends_on = None

RELEASE_TABLES = [
    "release_records",
    "release_candidates",
    "release_approvals",
    "release_gates",
    "release_gate_results",
    "release_strategies",
    "release_steps",
    "release_verifications",
    "release_locks",
    "feature_flags",
    "feature_flag_versions",
    "feature_flag_rules",
    "feature_flag_evaluations",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in RELEASE_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in reversed(RELEASE_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
