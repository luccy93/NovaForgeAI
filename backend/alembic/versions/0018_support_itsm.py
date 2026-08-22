"""Alembic migration: Customer Support & Service Management tables (Volume 54)

Revision ID: 0018_support_itsm
Revises: 0017_billing_platform
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_support_itsm"
down_revision = "0017_billing_platform"
branch_labels = None
depends_on = None

from app.core.database import Base
from app.support import models as support_models  # noqa — registers tables on Base.metadata

SUPPORT_TABLES = [
    "support_tickets",
    "support_messages",
    "support_assignments",
    "support_categories",
    "support_sla_policies",
    "support_sla_tracking",
    "support_escalations",
    "support_attachments",
    "support_knowledge_articles",
    "support_feedback",
    "support_automation_runs",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in SUPPORT_TABLES if name in Base.metadata.tables]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for name in reversed(SUPPORT_TABLES):
        try:
            op.drop_table(name)
        except Exception:
            pass
