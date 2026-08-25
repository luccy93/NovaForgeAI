"""Resilience platform (Volume 60 Commit 1) — additive-only.

Revision ID: 0024_resilience
Revises: 0023_observability
"""

from alembic import op

from app.core.database import Base
from app.resilience import models as _res  # noqa: F401
from app.observability import models as _obs  # noqa: F401
from app.aiml import models as _aiml  # noqa: F401
from app.datagov import models as _dg  # noqa: F401
from app.release import models as _rel  # noqa: F401

revision = "0024_resilience"
down_revision = "0023_observability"
branch_labels = None
depends_on = None

RES_TABLES = [
    "resilience_profiles",
    "resilience_backup_policies",
    "resilience_backups",
    "resilience_backup_verifications",
    "resilience_restore_jobs",
    "resilience_recovery_plans",
    "resilience_recovery_steps",
    "resilience_disaster_events",
    "resilience_failover_records",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in RES_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in reversed(RES_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
