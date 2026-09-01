"""AI Developer Experience — Volume 67 Commit 1.

6 new tables (code_workspaces, code_patches, code_reviews,
code_review_findings, code_test_runs, code_ai_usage) plus additive
embedding-provenance columns on the existing code_indexes and
code_index_versions tables. No existing schema is altered destructively.
"""

from alembic import op
import sqlalchemy as sa

from app.core.database import Base
from app.ai_dev import models as _ai_dev_models  # noqa: F401  (register tables)

revision = "0034_ai_dev"
down_revision = "0033_workflow_human"
branch_labels = None
depends_on = None

AI_DEV_TABLES = [
    "code_workspaces",
    "code_patches",
    "code_reviews",
    "code_review_findings",
    "code_test_runs",
    "code_ai_usage",
]

_ADDITIVE_COLUMNS = {
    "code_indexes": [
        ("embedding_version", sa.String(50)),
        ("embedding_dimension", sa.Integer()),
    ],
    "code_index_versions": [
        ("embedding_version", sa.String(50)),
        ("embedding_dimension", sa.Integer()),
    ],
}


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in AI_DEV_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)

    for table, cols in _ADDITIVE_COLUMNS.items():
        try:
            existing = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        except Exception:
            continue
        for name, coltype in cols:
            if name not in existing:
                op.add_column(table, sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    for table, cols in _ADDITIVE_COLUMNS.items():
        for name, _ in cols:
            try:
                op.drop_column(table, name)
            except Exception:
                pass
    for t in reversed(AI_DEV_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass