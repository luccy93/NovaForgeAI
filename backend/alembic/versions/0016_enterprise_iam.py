"""Alembic migration: Enterprise IAM Platform tables (Volume 52)

Revision ID: 0016_enterprise_iam
Revises: 0015_knowledge_graph
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_enterprise_iam"
down_revision = "0015_knowledge_graph"
branch_labels = None
depends_on = None

from app.core.database import Base
from app.iam import models as iam_models

IAM_TABLES = [
    "iam_workspaces",
    "iam_projects",
    "iam_teams",
    "iam_team_members",
    "iam_memberships",
    "iam_roles",
    "iam_resource_policies",
    "iam_service_accounts",
    "iam_api_keys",
    "iam_sessions",
    "iam_identity_providers",
    "iam_access_requests",
    "iam_break_glass_sessions",
    "iam_quota_policies",
    "iam_domain_verifications",
    "iam_audit_logs",
    "iam_access_reviews",
    "iam_privilege_analyses",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in IAM_TABLES if name in Base.metadata.tables]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for name in reversed(IAM_TABLES):
        try:
            op.drop_table(name)
        except Exception:
            pass
