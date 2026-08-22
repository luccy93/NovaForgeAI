"""Alembic migration: Knowledge Graph Platform tables (Volume 51)

Revision ID: 0015_knowledge_graph
Revises: 0014_analytics_platform
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_knowledge_graph"
down_revision = "0014_analytics_platform"
branch_labels = None
depends_on = None

from app.core.database import Base
from app.knowledge_graph import models as kg_models

KG_TABLES = [
    "kg_entities",
    "kg_relationships",
    "kg_entity_aliases",
    "kg_snapshots",
    "kg_sync_jobs",
    "kg_quality_metrics",
    "kg_audit_log",
    "kg_authorization_policies",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in KG_TABLES if name in Base.metadata.tables]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for name in reversed(KG_TABLES):
        try:
            op.drop_table(name)
        except Exception:
            pass
