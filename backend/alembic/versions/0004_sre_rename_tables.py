"""SRE (Volume 35) - rename tables to spec entity names.

Aligns the physical table names with the mandated Volume 35 database
entities:
    sre_service_dependencies -> sre_dependencies
    sre_maintenance_windows  -> sre_maintenance
    sre_capacity_metrics     -> sre_capacity
    sre_backup_jobs          -> sre_backups

Revision ID: 0004_sre_rename_tables
Revises: 0003_sre
Create Date: 2026-08-16
"""
from alembic import op

revision = "0004_sre_rename_tables"
down_revision = "0003_sre"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("sre_service_dependencies", "sre_dependencies")
    op.rename_table("sre_maintenance_windows", "sre_maintenance")
    op.rename_table("sre_capacity_metrics", "sre_capacity")
    op.rename_table("sre_backup_jobs", "sre_backups")


def downgrade() -> None:
    op.rename_table("sre_backups", "sre_backup_jobs")
    op.rename_table("sre_capacity", "sre_capacity_metrics")
    op.rename_table("sre_maintenance", "sre_maintenance_windows")
    op.rename_table("sre_dependencies", "sre_service_dependencies")
