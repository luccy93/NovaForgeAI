"""AI Developer Experience agents — Volume 67 Commit 2.

Creates the six C2 tables (code_agent_runs, code_agent_plans,
code_agent_checkpoints, code_agent_feedbacks, code_benchmarks,
code_benchmark_runs). Additive only; no existing schema is altered.
"""

from alembic import op
import sqlalchemy as sa

from app.core.database import Base
from app.ai_dev import models as _ai_dev_models  # noqa: F401

revision = "0035_ai_dev_agent"
down_revision = "0034_ai_dev"
branch_labels = None
depends_on = None

C2_TABLES = [
    "code_agent_runs",
    "code_agent_plans",
    "code_agent_checkpoints",
    "code_agent_feedbacks",
    "code_benchmarks",
    "code_benchmark_runs",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in C2_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in reversed(C2_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass