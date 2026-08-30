"""Data Platform — Volume 65 Commit 1 (12 tables, additive-only)."""

from alembic import op

from app.core.database import Base
from app.data_platform import models as _dp  # noqa: F401

revision = "0030_data_platform"
down_revision = "0029_zero_trust"
branch_labels = None
depends_on = None

DATA_TABLES = [
    "data_datasets",
    "data_dataset_versions",
    "data_sources",
    "data_schemas",
    "data_schema_versions",
    "data_pipelines",
    "data_pipeline_runs",
    "data_quality_rules",
    "data_quality_results",
    "data_lineage_edges",
    "data_streams",
    "data_checkpoints",
]


def upgrade() -> None:
    bind = op.get_bind()
    tables = [Base.metadata.tables[t] for t in DATA_TABLES if t in Base.metadata.tables]
    if tables:
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)
    # PostgreSQL GIN indexes for searchable metadata (additive, try/except for SQLite)
    try:
        op.create_index("ix_data_datasets_name_gin", "data_datasets", ["name"], postgresql_using="gin")
    except Exception:
        pass


def downgrade() -> None:
    for t in reversed(DATA_TABLES):
        try:
            op.drop_table(t)
        except Exception:
            pass
    try:
        op.drop_index("ix_data_datasets_name_gin", table_name="data_datasets")
    except Exception:
        pass
