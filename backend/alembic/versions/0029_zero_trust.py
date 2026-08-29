"""Zero Trust — Volume 64 Commit 1 (additive-only).

PostgreSQL authoritative for session/credential metadata. Redis cache only.
Extends iam_sessions with zero-trust fields, creates 3 new tables.
Never stores plaintext secrets — only hashes.
"""

import sqlalchemy as sa
from alembic import op

from app.core.database import Base
from app.zero_trust import models as _zt  # noqa: F401
from app.iam import models as _iam  # noqa: F401

revision = "0029_zero_trust"
down_revision = "0028_secops"
branch_labels = None
depends_on = None

ZT_TABLES = [
    "iam_credentials_metadata",
    "iam_privileged_access",
    "iam_identity_risk_snapshots",
]

# Columns to add to iam_sessions (additive, nullable/default)
SESSION_COLS = [
    sa.Column("session_id_hash", sa.String(length=128), nullable=True),
    sa.Column("identity_id", sa.String(length=64), nullable=True),
    sa.Column("tenant_id", sa.Uuid(), nullable=True),
    sa.Column("scope", sa.JSON(), nullable=True),
    sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
    sa.Column("device_context_hash", sa.String(length=128), nullable=True),
    sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("revocation_version", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("risk_state", sa.String(length=16), nullable=False, server_default="LOW"),
    sa.Column("policy_version", sa.String(length=32), nullable=False, server_default="1.0"),
    sa.Column("region", sa.String(length=64), nullable=True),
]


def upgrade() -> None:
    bind = op.get_bind()
    # Create new tables
    tables = [Base.metadata.tables[t] for t in ZT_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)
    # Extend iam_sessions
    for col in SESSION_COLS:
        try:
            op.add_column("iam_sessions", col)
        except Exception:
            pass
    # Create indexes for new columns where needed (unique for session_id_hash already via column, but ensure)
    try:
        op.create_index("ix_iam_sessions_session_id_hash", "iam_sessions", ["session_id_hash"], unique=True)
    except Exception:
        pass
    try:
        op.create_index("ix_iam_sessions_tenant_id", "iam_sessions", ["tenant_id"])
    except Exception:
        pass
    try:
        op.create_index("ix_iam_sessions_identity_id", "iam_sessions", ["identity_id"])
    except Exception:
        pass


def downgrade() -> None:
    for t in reversed(ZT_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
    for col in reversed(SESSION_COLS):
        try:
            op.drop_column("iam_sessions", col.name)  # type: ignore[attr-defined]
        except Exception:
            pass
    for idx in ["ix_iam_sessions_session_id_hash", "ix_iam_sessions_tenant_id", "ix_iam_sessions_identity_id"]:
        try:
            op.drop_index(idx, table_name="iam_sessions")
        except Exception:
            pass
