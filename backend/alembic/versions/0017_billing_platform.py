"""Alembic migration: Production-Grade Billing Platform tables (Volume 53)

Revision ID: 0017_billing_platform
Revises: 0016_enterprise_iam
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_billing_platform"
down_revision = "0016_enterprise_iam"
branch_labels = None
depends_on = None

from app.core.database import Base
from app.billing import models as billing_models  # noqa — registers tables on Base.metadata

BILLING_TABLES = [
    "billing_plans",
    "billing_subscriptions",
    "billing_invoices",
    "billing_payments",
    "billing_usage_metering",
    "billing_credits",
    "billing_credit_transactions",
    "billing_coupons",
    "billing_coupon_redemptions",
    "billing_budgets",
    "billing_marketplace_records",
    "billing_dunning_records",
    "billing_reconciliation",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in BILLING_TABLES if name in Base.metadata.tables]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for name in reversed(BILLING_TABLES):
        try:
            op.drop_table(name)
        except Exception:
            pass
