"""knowledge foundation — Volume 68 Commit 1

Creates the eight C1 tables (knowledge_sources, knowledge_documents,
knowledge_chunks, knowledge_entities, knowledge_links,
knowledge_ingestion_jobs, knowledge_queries, knowledge_query_results).
Additive only; no existing schema is altered.
"""

from alembic import op
import sqlalchemy as sa

from app.core.database import Base
from app.knowledge import models as _knowledge_models  # noqa: F401

revision = "0036_knowledge_foundation"
down_revision = "0035_ai_dev_agent"
branch_labels = None
depends_on = None

KNOWLEDGE_TABLES = [
    "knowledge_sources",
    "knowledge_documents",
    "knowledge_chunks",
    "knowledge_entities",
    "knowledge_links",
    "knowledge_ingestion_jobs",
    "knowledge_queries",
    "knowledge_query_results",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in KNOWLEDGE_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in reversed(KNOWLEDGE_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
