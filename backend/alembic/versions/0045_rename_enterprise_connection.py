"""rename colliding enterprise connection table — volume 72 c1

Revision ID: 0045_rename_enterprise_connection
Revises: 0044_merge_sre_rename
Create Date: 2026-09-06 00:00:00.000000

The legacy enterprise IntegrationConnection model shared
__tablename__ "integration_connections" with the governed V70 model,
so only one schema survived in metadata. The enterprise model now
maps to "enterprise_integration_connections". This migration renames
an existing legacy-shaped table (identified by the organization_id
column) and is a no-op otherwise. Historical migrations untouched.
"""

from alembic import op
import sqlalchemy as sa

revision = "0045_rename_enterprise_connection"
down_revision = "0044_merge_sre_rename"
branch_labels = None
depends_on = None

OLD_TABLE = "integration_connections"
NEW_TABLE = "enterprise_integration_connections"


def _columns(bind, table):
    try:
        return {c["name"] for c in sa.inspect(bind).get_columns(table)}
    except Exception:
        return set()


def _tables(bind):
    try:
        return set(sa.inspect(bind).get_table_names())
    except Exception:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if OLD_TABLE not in tables or NEW_TABLE in tables:
        return
    try:
        # Only rename the legacy enterprise shape, never the governed one.
        if "organization_id" in _columns(bind, OLD_TABLE):
            op.rename_table(OLD_TABLE, NEW_TABLE)
    except Exception:
        pass


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if NEW_TABLE not in tables or OLD_TABLE in tables:
        return
    try:
        op.rename_table(NEW_TABLE, OLD_TABLE)
    except Exception:
        pass
