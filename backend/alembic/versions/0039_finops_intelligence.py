"""governed finops intelligence — volume 69 c2

Revision ID: 0039_finops_intelligence
Revises: 0038_finops_foundation
Create Date: 2026-09-04 00:00:00.000000
"""

from alembic import op
from app.core.database import Base
from app.finops import governed_models_c2 as _finops_c2_models  # noqa: F401

revision = "0039_finops_intelligence"
down_revision = "0038_finops_foundation"
branch_labels = None
depends_on = None

C2_TABLES = [
    "finops_forecasts",
    "finops_anomalies",
    "finops_recommendations",
    "finops_policies",
    "finops_policy_decisions",
    "finops_chargeback_reports",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in C2_TABLES if name in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for table_name in reversed(C2_TABLES):
        try:
            op.drop_table(table_name)
        except Exception:
            pass
