"""Multi-Region (Volume 62 Commit 1) — additive-only.

Revision ID: 0026_multiregion
Revises: 0025_performance
"""

from alembic import op

from app.core.database import Base
from app.regions import models as _regions  # noqa: F401

revision = "0026_multiregion"
down_revision = "0025_performance"
branch_labels = None
depends_on = None

REGION_TABLES = [
    "regions",
    "region_capabilities",
    "tenant_region_placements",
    "region_routing_policies",
    "region_replication_records",
    "region_failover_records",
    "region_health_snapshots",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in REGION_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in reversed(REGION_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
