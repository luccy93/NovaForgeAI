"""Alembic migration: Incident Response Platform tables (Volume 49)

Revision ID: 0013
Revises: 0012_quality_engine
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text

revision = "0013_incident_platform"
down_revision = "0012_quality_engine"
branch_labels = None
depends_on = None

from app.core.database import Base
from app.incident import models as incident_models

INCIDENT_TABLES = [
    "incident_incidents",
    "incident_events",
    "incident_alerts",
    "incident_hypotheses",
    "incident_actions",
    "incident_runbooks",
    "incident_postmortems",
    "incident_action_items",
    "incident_escalation_policies",
    "incident_alert_policies",
    "incident_reliability_metrics",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in INCIDENT_TABLES if name in Base.metadata.tables]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for name in reversed(INCIDENT_TABLES):
        try:
            op.drop_table(name)
        except Exception:
            pass
