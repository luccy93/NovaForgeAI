"""SecOps — Volume 63 Commit 1 (additive-only, 7 tables)."""

from alembic import op

from app.core.database import Base
from app.secops import models as _secops  # noqa: F401

revision = "0028_secops"
down_revision = "0027_multiregion_hardening"
branch_labels = None
depends_on = None

SECOPS_TABLES = [
    "security_detection_rules",
    "security_alerts",
    "secops_findings",
    "security_cases",
    "security_case_evidence",
    "security_indicators",
    "security_risk_snapshots",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in SECOPS_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    for t in reversed(SECOPS_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
