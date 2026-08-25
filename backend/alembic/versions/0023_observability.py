"""Observability unified platform (Volume 59 Commit 1) — additive-only.

Revision ID: 0023_observability
Revises: 0022_aiml
"""

from alembic import op

from app.core.database import Base
from app.observability import models as _obs  # noqa: F401
from app.aiml import models as _aiml  # noqa: F401
from app.datagov import models as _dg  # noqa: F401
from app.release import models as _rel  # noqa: F401

revision = "0023_observability"
down_revision = "0022_aiml"
branch_labels = None
depends_on = None

OBS_TABLES = [
    "observability_services",
    "observability_alert_rules",
    "observability_alerts",
    "observability_slos",
    "observability_synthetic_checks",
    "observability_health_snapshots",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in OBS_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in reversed(OBS_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
