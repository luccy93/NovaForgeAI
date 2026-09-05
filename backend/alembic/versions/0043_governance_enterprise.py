"""central governance enterprise — volume 71 c2

Revision ID: 0043_governance_enterprise
Revises: 0042_governance_foundation
Create Date: 2026-09-05 00:00:00.000000
"""

from alembic import op
from app.core.database import Base
from app.governance import plane_models_c2 as _governance_c2  # noqa: F401

revision = "0043_governance_enterprise"
down_revision = "0042_governance_foundation"
branch_labels = None
depends_on = None

C2_TABLES = [
    "governance_plane_evidence",
    "governance_plane_drift",
    "governance_plane_reports",
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
