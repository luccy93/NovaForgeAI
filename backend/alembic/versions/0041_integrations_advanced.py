"""governed integrations advanced — volume 70 c2

Revision ID: 0041_integrations_advanced
Revises: 0040_integrations_foundation
Create Date: 2026-09-05 00:00:00.000000
"""

from alembic import op
from app.core.database import Base
from app.integrations import governed_models_c2 as _integrations_c2  # noqa: F401

revision = "0041_integrations_advanced"
down_revision = "0040_integrations_foundation"
branch_labels = None
depends_on = None

C2_TABLES = [
    "integration_oauth_connections",
    "integration_connector_syncs",
    "integration_inbound_webhooks",
    "integration_policies",
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
