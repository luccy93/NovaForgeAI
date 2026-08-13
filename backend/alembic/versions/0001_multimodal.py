"""Multimodal AI & Computer Vision (Volume 32) - schema migration.

Revision ID: 0001_multimodal
Revises:
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

revision = "0001_multimodal"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else "postgresql"
    json_type = JSONB if dialect == "postgresql" else sa.JSON

    # ------------------------------------------------------------------ assets
    op.create_table(
        "multimodal_assets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("asset_id", sa.String(64), nullable=False, unique=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("workspace_id", sa.String(64), default=""),
        sa.Column("repository_id", sa.String(64), default=""),
        sa.Column("source", sa.String(32), default="upload"),
        sa.Column("file_name", sa.String(255), default=""),
        sa.Column("file_type", sa.String(32), default=""),
        sa.Column("mime_type", sa.String(64), default=""),
        sa.Column("modality", sa.String(16), nullable=False, index=True),
        sa.Column("size_bytes", sa.BigInteger, default=0),
        sa.Column("checksum_sha256", sa.String(64), default=""),
        sa.Column("encoding", sa.String(16), default="utf-8"),
        sa.Column("status", sa.String(16), default="uploaded", index=True),
        sa.Column("storage_key", sa.String(255), default=""),
        sa.Column("url", sa.String(512), default=""),
        sa.Column("metadata", json_type, default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_multimodal_assets_org_modality",
                    "multimodal_assets", ["organization_id", "modality"])

    # ------------------------------------------------------------------- jobs
    op.create_table(
        "multimodal_jobs",
        sa.Column("job_id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("asset_id", sa.String(64), default=""),
        sa.Column("status", sa.String(16), nullable=False, default="queued", index=True),
        sa.Column("attempt", sa.Integer, default=0),
        sa.Column("max_attempts", sa.Integer, default=3),
        sa.Column("worker", sa.String(64), default=""),
        sa.Column("error", sa.Text, default=""),
        sa.Column("result", json_type, default=None),
        sa.Column("payload", json_type, default=dict),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------- extractions
    op.create_table(
        "multimodal_extractions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("asset_id", sa.String(64), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("modality", sa.String(16), nullable=False),
        sa.Column("engine", sa.String(64), default=""),
        sa.Column("page_count", sa.Integer, default=0),
        sa.Column("full_text", sa.Text, default=""),
        sa.Column("metadata", json_type, default=dict),
        sa.Column("scanned_hint", sa.String(255), default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "multimodal_chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("asset_id", sa.String(64), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("modality", sa.String(16), nullable=False),
        sa.Column("chunk_index", sa.Integer, default=0),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("heading", sa.String(255), default=""),
        sa.Column("page", sa.Integer, default=0),
        sa.Column("token_count", sa.Integer, default=0),
        sa.Column("embedder", sa.String(32), default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_multimodal_chunks_org_asset",
                    "multimodal_chunks", ["organization_id", "asset_id"])

    op.create_table(
        "multimodal_embeddings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("chunk_id", sa.String(64), nullable=False, index=True),
        sa.Column("asset_id", sa.String(64), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("modality", sa.String(16), nullable=False),
        sa.Column("embedder", sa.String(32), default=""),
        sa.Column("dimension", sa.Integer, default=128),
        sa.Column("vector", ARRAY(sa.Float), default=None),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -------------------------------------------------------------- diagrams
    op.create_table(
        "multimodal_diagrams",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("asset_id", sa.String(64), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("parser", sa.String(64), default="geometric-heuristic"),
        sa.Column("node_count", sa.Integer, default=0),
        sa.Column("edge_count", sa.Integer, default=0),
        sa.Column("result", json_type, default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "multimodal_diagram_nodes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("diagram_id", sa.String(64), nullable=False, index=True),
        sa.Column("node_id", sa.String(64), nullable=False),
        sa.Column("label", sa.String(255), default=""),
        sa.Column("kind", sa.String(32), default="component"),
        sa.Column("box", json_type, default=None),
        sa.Column("confidence", sa.Float, default=0.0),
    )

    op.create_table(
        "multimodal_diagram_edges",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("diagram_id", sa.String(64), nullable=False, index=True),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), default="arrow"),
        sa.Column("label", sa.String(255), default=""),
        sa.Column("confidence", sa.Float, default=0.0),
    )

    # -------------------------------------------------------- visual regress
    op.create_table(
        "multimodal_screenshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("asset_id", sa.String(64), nullable=False, index=True),
        sa.Column("url", sa.String(512), default=""),
        sa.Column("viewport", sa.String(32), default=""),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "multimodal_comparisons",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("baseline_id", sa.String(64), nullable=False),
        sa.Column("candidate_id", sa.String(64), nullable=False),
        sa.Column("mean_delta", sa.Float, default=0.0),
        sa.Column("diff_ratio", sa.Float, default=0.0),
        sa.Column("diff_pixels", sa.Integer, default=0),
        sa.Column("verdict", sa.String(16), default="identical"),
        sa.Column("changed_bbox", json_type, default=None),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ----------------------------------------------------------------- video
    op.create_table(
        "multimodal_videos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("asset_id", sa.String(64), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("duration_s", sa.Float, default=0.0),
        sa.Column("width", sa.Integer, default=0),
        sa.Column("height", sa.Integer, default=0),
        sa.Column("fps", sa.Float, default=0.0),
        sa.Column("codec", sa.String(32), default=""),
        sa.Column("scene_count", sa.Integer, default=0),
        sa.Column("transcript", sa.Text, default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "multimodal_video_scenes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("video_id", sa.String(64), nullable=False, index=True),
        sa.Column("scene_index", sa.Integer, default=0),
        sa.Column("timestamp_s", sa.Float, default=0.0),
        sa.Column("frame_path", sa.String(512), default=""),
        sa.Column("ocr_text", sa.Text, default=""),
    )

    # ----------------------------------------------------------------- audio
    op.create_table(
        "multimodal_audio",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("asset_id", sa.String(64), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("duration_s", sa.Float, default=0.0),
        sa.Column("provider", sa.String(32), default=""),
        sa.Column("status", sa.String(16), default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "multimodal_transcripts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("audio_id", sa.String(64), nullable=False, index=True),
        sa.Column("asset_id", sa.String(64), nullable=False, index=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("language", sa.String(8), default="en"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "multimodal_topics",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("audio_id", sa.String(64), nullable=False, index=True),
        sa.Column("topic", sa.String(64), nullable=False),
        sa.Column("keywords", ARRAY(sa.String), default=None),
        sa.Column("mentions", sa.Integer, default=0),
    )

    op.create_table(
        "multimodal_decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("audio_id", sa.String(64), nullable=False, index=True),
        sa.Column("sentence", sa.Text, nullable=False),
    )

    # --------------------------------------------------------------- memory
    op.create_table(
        "multimodal_memory",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("assets_ingested", sa.BigInteger, default=0),
        sa.Column("chunks_indexed", sa.BigInteger, default=0),
        sa.Column("ocr_calls", sa.BigInteger, default=0),
        sa.Column("vision_calls", sa.BigInteger, default=0),
        sa.Column("embed_calls", sa.BigInteger, default=0),
        sa.Column("rag_searches", sa.BigInteger, default=0),
        sa.Column("llm_calls", sa.BigInteger, default=0),
        sa.Column("cost_usd", sa.Float, default=0.0),
        sa.Column("bytes_ingested", sa.BigInteger, default=0),
        sa.Column("last_active", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "multimodal_cost_ledger",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(64), nullable=False, index=True),
        sa.Column("asset_id", sa.String(64), default=""),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), default=""),
        sa.Column("model", sa.String(64), default=""),
        sa.Column("tokens_in", sa.Integer, default=0),
        sa.Column("tokens_out", sa.Integer, default=0),
        sa.Column("cost_usd", sa.Float, default=0.0),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    tables = [
        "multimodal_cost_ledger", "multimodal_memory", "multimodal_decisions",
        "multimodal_topics", "multimodal_transcripts", "multimodal_audio",
        "multimodal_video_scenes", "multimodal_videos",
        "multimodal_comparisons", "multimodal_screenshots",
        "multimodal_diagram_edges", "multimodal_diagram_nodes",
        "multimodal_diagrams", "multimodal_embeddings", "multimodal_chunks",
        "multimodal_extractions", "multimodal_jobs", "multimodal_assets",
    ]
    for table in tables:
        op.drop_table(table)