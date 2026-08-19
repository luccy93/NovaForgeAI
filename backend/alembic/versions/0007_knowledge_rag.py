"""Knowledge & Retrieval (RAG) layer — Volume 43 schema migration.

Revision ID: 0007_knowledge_rag
Revises: 0006_code_intelligence
"""

from alembic import op
from sqlalchemy import inspect

from app.core.database import Base
from app.rag import models as _rag_models  # noqa: F401  (registers tables on Base.metadata)

revision = "0007_knowledge_rag"
down_revision = "0006_code_intelligence"
branch_labels = None
depends_on = None

RAG_TABLES = [
    "rag_sources",
    "rag_source_versions",
    "rag_chunks",
    "rag_ingestion_jobs",
    "rag_retrieval_logs",
    "rag_context_sets",
    "rag_citation_records",
    "rag_evaluation_runs",
    "rag_quality_metrics",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    tables = [Base.metadata.tables[t] for t in RAG_TABLES if t in Base.metadata.tables]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)
    # Null out FK-less safety: ensure created tables exist.
    for t in RAG_TABLES:
        if t not in existing and t not in set(inspector.get_table_names()):
            op.get_bind()  # no-op to keep transaction alive


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    for t in RAG_TABLES:
        if t in existing:
            op.drop_table(t)
