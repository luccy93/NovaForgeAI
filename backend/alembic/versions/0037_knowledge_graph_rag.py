"""knowledge graph, rag, and security additions — volume 68 c2

Revision ID: 0037_knowledge_graph_rag
Revises: 0036_knowledge_foundation
Create Date: 2026-09-03 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from app.core.database import Base
from app.knowledge import models as _knowledge_models  # noqa: F401

revision = "0037_knowledge_graph_rag"
down_revision = "0036_knowledge_foundation"
branch_labels = None
depends_on = None

C2_TABLES = [
    "knowledge_cache_entries",
    "knowledge_explanations",
    "knowledge_admin_audit",
    "knowledge_graph_communities",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in C2_TABLES if name in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(C2_TABLES):
        try:
            op.drop_table(table_name)
        except Exception:
            pass
