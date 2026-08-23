"""Marketplace ecosystem extensions — Volume 55 additive-only.

Revision ID: 0019_marketplace_ecosystem
Revises: 0018_support_itsm
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.core.database import Base
from app.marketplace import models as _mp_models  # noqa: F401 — registers tables on Base.metadata

revision = "0019_marketplace_ecosystem"
down_revision = "0018_support_itsm"
branch_labels = None
depends_on = None

MARKETPLACE_ECOSYSTEM_TABLES = [
    "marketplace_categories",
    "marketplace_health",
    "marketplace_emergency_blocks",
    "marketplace_license_policies",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    ecosystem_tables = [Base.metadata.tables[t] for t in MARKETPLACE_ECOSYSTEM_TABLES if t in Base.metadata.tables]
    if ecosystem_tables:
        Base.metadata.create_all(bind=bind, tables=ecosystem_tables, checkfirst=True)

    for table, col, col_type in [
        ("marketplace_packages", "release_channel", sa.String(32)),
        ("marketplace_packages", "provenance", sa.JSON()),
        ("marketplace_packages", "sbom", sa.JSON()),
        ("marketplace_packages", "moderation_status", sa.String(32)),
        ("marketplace_packages", "health_score", sa.Float()),
        ("marketplace_packages", "health_status", sa.String(32)),
        ("marketplace_releases", "release_channel", sa.String(32)),
        ("marketplace_releases", "provenance", sa.JSON()),
        ("marketplace_releases", "sbom_ref", sa.String(512)),
        ("marketplace_releases", "is_security_update", sa.Boolean()),
        ("marketplace_releases", "is_critical_update", sa.Boolean()),
        ("marketplace_releases", "is_breaking_update", sa.Boolean()),
        ("marketplace_installations", "dependency_lock", sa.JSON()),
        ("marketplace_installations", "rollout_strategy", sa.String(32)),
        ("marketplace_installations", "health_status", sa.String(32)),
        ("marketplace_installations", "license_policy_status", sa.String(32)),
    ]:
        try:
            cols = {c["name"] for c in inspector.get_columns(table)}
            if col not in cols:
                op.add_column(table, sa.Column(col, col_type, nullable=True))
        except Exception:
            pass


def downgrade() -> None:
    for t in reversed(MARKETPLACE_ECOSYSTEM_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
