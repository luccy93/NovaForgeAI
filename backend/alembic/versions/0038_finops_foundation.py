"""governed finops foundation — volume 69 c1

Revision ID: 0038_finops_foundation
Revises: 0037_knowledge_graph_rag
Create Date: 2026-09-04 00:00:00.000000
"""

from alembic import op
from app.core.database import Base
from app.finops import governed_models as _finops_models  # noqa: F401

revision = "0038_finops_foundation"
down_revision = "0037_knowledge_graph_rag"
branch_labels = None
depends_on = None

FINOPS_TABLES = [
    "finops_pricing_versions",
    "finops_cost_records",
    "finops_cost_allocations",
    "finops_budgets",
    "finops_budget_events",
    "finops_cost_aggregations",
    "finops_audit_log",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in FINOPS_TABLES if name in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for table_name in reversed(FINOPS_TABLES):
        try:
            op.drop_table(table_name)
        except Exception:
            pass
