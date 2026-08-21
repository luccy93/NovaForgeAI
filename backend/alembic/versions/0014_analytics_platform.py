"""Alembic migration: Unified Analytics Platform tables (Volume 50)

Revision ID: 0014
Revises: 0013_incident_platform
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text

revision = "0014_analytics_platform"
down_revision = "0013_incident_platform"
branch_labels = None
depends_on = None

from app.core.database import Base
from app.analytics import models as analytics_models

ANALYTICS_TABLES = [
    "analytics_events",
    "analytics_metric_definitions",
    "analytics_aggregates",
    "analytics_cost_records",
    "analytics_budgets",
    "analytics_alerts",
    "analytics_reports",
    "analytics_forecasts",
    "analytics_recommendations",
    "analytics_data_quality",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in ANALYTICS_TABLES if name in Base.metadata.tables]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for name in reversed(ANALYTICS_TABLES):
        try:
            op.drop_table(name)
        except Exception:
            pass
