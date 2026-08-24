"""Data Governance (Volume 57) — additive-only.

Revision ID: 0021_datagov
Revises: 0020_release_progressive_delivery
"""

from alembic import op

from app.core.database import Base
from app.datagov import models as _dg  # noqa: F401

revision = "0021_datagov"
down_revision = "0020_release_progressive_delivery"
branch_labels = None
depends_on = None

DG_TABLES = [
    "governance_data_assets",
    "governance_classifications",
    "governance_lineage",
    "governance_retention_policies",
    "governance_data_requests",
    "governance_exports",
    "governance_processors",
    "governance_consents",
    "governance_policy_decisions",
    "governance_controls",
    "governance_control_evidence",
    "governance_legal_holds",
    "governance_exceptions",
    "governance_dlp_events",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in DG_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in reversed(DG_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
