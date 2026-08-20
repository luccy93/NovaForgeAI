"""Unified DevSecOps Security Platform (Volume 47).

Revision ID: 0011_security_platform
Revises: 0010_delivery
"""

from alembic import op
from sqlalchemy import inspect

from app.core.database import Base
from app.security import models as _security_models  # noqa: F401

revision = "0011_security_platform"
down_revision = "0010_delivery"
branch_labels = None
depends_on = None

SECURITY_TABLES = [
    "security_scans",
    "security_findings",
    "security_vulnerabilities",
    "security_sboms",
    "security_sbom_components",
    "security_assets",
    "security_policies",
    "security_policy_evaluations",
    "security_risk_acceptances",
    "security_fingerprints",
    "security_remediations",
    "security_provenance",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    tables = [
        Base.metadata.tables[t]
        for t in SECURITY_TABLES
        if t in Base.metadata.tables
    ]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in SECURITY_TABLES:
        op.drop_table(t)
