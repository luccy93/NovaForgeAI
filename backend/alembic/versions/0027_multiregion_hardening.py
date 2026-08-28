"""Multi-Region hardening (Volume 62 Commit 2) — additive-only.

Revision ID: 0027_multiregion_hardening
Revises: 0026_multiregion
"""

from alembic import op
import sqlalchemy as sa

from app.core.database import Base
from app.regions import models as _regions  # noqa: F401
from app.regions import models_c2 as _regions_c2  # noqa: F401

revision = "0027_multiregion_hardening"
down_revision = "0026_multiregion"
branch_labels = None
depends_on = None

REGION_C2_TABLES = [
    "region_leases",
    "tenant_migrations",
    "region_traffic_shifts",
    "replication_conflicts",
    "config_drift",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in REGION_C2_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)
    # Additive: Region.metadata_json introduced with Commit 2 hardening
    try:
        op.add_column("regions", sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"))
    except Exception:
        pass


def downgrade() -> None:
    for t in reversed(REGION_C2_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
    try:
        op.drop_column("regions", "metadata_json")
    except Exception:
        pass
