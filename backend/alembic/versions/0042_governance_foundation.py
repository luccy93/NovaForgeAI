"""central governance plane foundation — volume 71 c1

Revision ID: 0042_governance_foundation
Revises: 0041_integrations_advanced
Create Date: 2026-09-05 00:00:00.000000
"""

from alembic import op
from app.core.database import Base
from app.governance import plane_models as _governance_models  # noqa: F401

revision = "0042_governance_foundation"
down_revision = "0041_integrations_advanced"
branch_labels = None
depends_on = None

GOVERNANCE_TABLES = [
    "governance_plane_policies",
    "governance_plane_policy_versions",
    "governance_plane_bindings",
    "governance_plane_evaluations",
    "governance_plane_decisions",
    "governance_plane_exceptions",
    "governance_plane_exception_approvals",
    "governance_plane_posture_snapshots",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in GOVERNANCE_TABLES if name in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for table_name in reversed(GOVERNANCE_TABLES):
        try:
            op.drop_table(table_name)
        except Exception:
            pass
