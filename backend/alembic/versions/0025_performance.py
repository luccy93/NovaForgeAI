"""Performance (Volume 61 Commit 1) — additive-only.

Revision ID: 0025_performance
Revises: 0024_resilience
"""

from alembic import op

from app.core.database import Base
from app.performance import models as _perf  # noqa: F401
from app.observability import models as _obs  # noqa: F401
from app.aiml import models as _aiml  # noqa: F401
from app.datagov import models as _dg  # noqa: F401
from app.release import models as _rel  # noqa: F401
from app.resilience import models as _res  # noqa: F401

revision = "0025_performance"
down_revision = "0024_resilience"
branch_labels = None
depends_on = None

PERF_TABLES = [
    "performance_budgets",
    "performance_service_metrics",
    "performance_snapshots",
    "capacity_policies",
    "resource_pools",
    "performance_recommendations",
    "scaling_events",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in PERF_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in reversed(PERF_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
