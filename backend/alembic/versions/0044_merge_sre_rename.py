"""merge dangling sre rename branch — volume 72 c1

Revision ID: 0044_merge_sre_rename
Revises: 0043_governance_enterprise, 0004_sre_rename_tables
Create Date: 2026-09-06 00:00:00.000000

Merges the fork created when 0004_sre_rename_tables and
0004_compliance_framework both descended from 0003_sre. Applies the
SRE table renames idempotently (only when the old name exists and the
new name does not), matching backend/app/sre/models.py. Does not
modify any historical migration.
"""

from alembic import op
import sqlalchemy as sa

revision = "0044_merge_sre_rename"
down_revision = ("0043_governance_enterprise", "0004_sre_rename_tables")
branch_labels = None
depends_on = None

RENAMES = [
    ("sre_service_dependencies", "sre_dependencies"),
    ("sre_maintenance_windows", "sre_maintenance"),
    ("sre_capacity_metrics", "sre_capacity"),
    ("sre_backup_jobs", "sre_backups"),
]


def _tables(bind):
    inspector = sa.inspect(bind)
    try:
        return set(inspector.get_table_names())
    except Exception:
        return set()


def upgrade() -> None:
    bind = op.get_bind()
    existing = _tables(bind)
    for old_name, new_name in RENAMES:
        try:
            if old_name in existing and new_name not in existing:
                op.rename_table(old_name, new_name)
        except Exception:
            pass


def downgrade() -> None:
    bind = op.get_bind()
    existing = _tables(bind)
    for old_name, new_name in reversed(RENAMES):
        try:
            if new_name in existing and old_name not in existing:
                op.rename_table(new_name, old_name)
        except Exception:
            pass
