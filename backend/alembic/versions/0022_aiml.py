"""AIML (Volume 58) — additive-only.

Revision ID: 0022_aiml
Revises: 0021_datagov
"""

from alembic import op

from app.core.database import Base
from app.aiml import models as _aiml  # noqa: F401

revision = "0022_aiml"
down_revision = "0021_datagov"
branch_labels = None
depends_on = None

AIML_TABLES = [
    "ai_model_registry",
    "ai_model_versions",
    "ai_provider_registry",
    "ai_prompt_registry",
    "ai_prompt_versions",
    "ai_evaluation_suites",
    "ai_evaluation_runs",
    "ai_guardrails",
    "ai_risk_records",
    "ai_model_cards",
    "ai_system_cards",
    "ai_approval_requests",
    "ai_monitoring_snapshots",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in AIML_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in reversed(AIML_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
