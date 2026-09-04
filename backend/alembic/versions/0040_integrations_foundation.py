"""governed integrations foundation — volume 70 c1

Revision ID: 0040_integrations_foundation
Revises: 0039_finops_intelligence
Create Date: 2026-09-04 00:00:00.000000
"""

from alembic import op
from app.core.database import Base
from app.integrations import governed_models as _integrations_models  # noqa: F401

revision = "0040_integrations_foundation"
down_revision = "0039_finops_intelligence"
branch_labels = None
depends_on = None

INTEGRATIONS_TABLES = [
    "integrations",
    "integration_versions",
    "integration_connections",
    "integration_credentials",
    "integration_executions",
    "integration_health_checks",
    "integration_webhooks",
    "integration_webhook_deliveries",
    "integration_api_subscriptions",
    "integration_audit_log",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in INTEGRATIONS_TABLES if name in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for table_name in reversed(INTEGRATIONS_TABLES):
        try:
            op.drop_table(table_name)
        except Exception:
            pass
