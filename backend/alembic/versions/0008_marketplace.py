"""Enterprise Marketplace (Volume 44) — schema migration.

Revision ID: 0008_marketplace
Revises: 0007_knowledge_rag
"""

from alembic import op
from sqlalchemy import inspect

from app.core.database import Base
from app.marketplace import models as _mp_models  # noqa: F401  (registers tables on Base.metadata)

revision = "0008_marketplace"
down_revision = "0007_knowledge_rag"
branch_labels = None
depends_on = None

MARKETPLACE_TABLES = [
    "marketplace_publishers",
    "marketplace_packages",
    "marketplace_releases",
    "marketplace_permissions",
    "marketplace_dependencies",
    "marketplace_installations",
    "marketplace_reviews",
    "marketplace_reports",
    "marketplace_security_scans",
    "marketplace_package_events",
    "marketplace_package_usage",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    tables = [Base.metadata.tables[t] for t in MARKETPLACE_TABLES if t in Base.metadata.tables]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)
    for t in MARKETPLACE_TABLES:
        if t not in existing and t not in set(inspector.get_table_names()):
            op.get_bind()  # keep transaction alive


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    for t in MARKETPLACE_TABLES:
        if t in existing:
            op.drop_table(t)
