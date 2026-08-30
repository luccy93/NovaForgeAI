"""Lakehouse & streaming intelligence — Volume 65 Commit 2 (5 tables, additive)."""

from alembic import op

from app.core.database import Base
from app.data_platform import models as _dp  # noqa: F401
from app.data_platform import models_lakehouse as _lh  # noqa: F401

revision = "0031_data_lakehouse"
down_revision = "0030_data_platform"
branch_labels = None
depends_on = None

LAKE_TABLES = [
    "data_products",
    "data_domains",
    "data_freshness",
    "data_drift_events",
    "data_replay_jobs",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in LAKE_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in reversed(LAKE_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
