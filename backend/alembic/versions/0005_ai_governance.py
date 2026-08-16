"""AI Governance (Volume 37) - schema migration.

Revision ID: 0005_ai_governance
Revises: 0004_compliance_framework
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_ai_governance"
down_revision = "0004_compliance_framework"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ai_assets ────────────────────────────────────────────────────────
    op.create_table(
        "ai_assets",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(64), nullable=False),  # model, agent, prompt, tool, workflow, rag, application
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),  # draft, assessment_required, evaluation_required, approved, restricted, production, monitoring, suspended, retired
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("capabilities", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(32), server_default="medium", nullable=False),  # low, medium, high, critical
        sa.Column("environment", sa.String(32), server_default="production", nullable=False),  # development, staging, production, dr, sandbox, testing
        sa.Column("data_policy", sa.Text(), nullable=True),
        sa.Column("evaluation_status", sa.String(32), server_default="not_evaluated", nullable=False),  # not_evaluated, pending, passed, failed, expired
        sa.Column("approval_status", sa.String(32), server_default="pending", nullable=False),  # pending, approved, rejected
        sa.Column("approval_by", sa.String(128), nullable=True),
        sa.Column("approval_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_reason", sa.Text(), nullable=True),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dependencies", sa.Text(), nullable=True),  # JSON-comma-separated asset IDs
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_assets_org", "ai_assets", ["org_id"])
    op.create_index("ix_ai_assets_type", "ai_assets", ["type"])
    op.create_index("ix_ai_assets_status", "ai_assets", ["status"])

    # ── ai_asset_versions ────────────────────────────────────────────────
    op.create_table(
        "ai_asset_versions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("release_notes", sa.Text(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("approval_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_reason", sa.Text(), nullable=True),
        sa.Column("rollback_to_version", sa.String(64), nullable=True),
        sa.Column("migration_plan", sa.Text(), nullable=True),
        sa.Column("evaluation_requirements", sa.Text(), nullable=True),  # JSON
        sa.Column("evaluation_status", sa.String(32), server_default="not_evaluated", nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_by", sa.String(128), nullable=True),
        sa.Column("quality_metrics", sa.Text(), nullable=True),  # JSON
        sa.Column("safety_metrics", sa.Text(), nullable=True),  # JSON
        sa.Column("cost_metrics", sa.Text(), nullable=True),  # JSON
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_asset_versions_asset", "ai_asset_versions", ["asset_id"])

    # ── ai_models ──────────────────────────────────────────────────────────
    op.create_table(
        "ai_models",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(128), nullable=True),
        sa.Column("model", sa.String(256), nullable=True),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("capabilities", sa.Text(), nullable=True),
        sa.Column("context_limit", sa.Integer(), nullable=True),
        sa.Column("modalities", sa.Text(), nullable=True),  # JSON array
        sa.Column("cost_metadata", sa.Text(), nullable=True),  # JSON
        sa.Column("regions", sa.Text(), nullable=True),  # JSON array
        sa.Column("data_use_restrictions", sa.Text(), nullable=True),  # JSON
        sa.Column("approval_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("approval_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_reason", sa.Text(), nullable=True),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_level", sa.String(32), server_default="medium", nullable=False),
sa.Column("status", sa.String(32), server_default="draft", nullable=False),
        sa.Column("deprecation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replacement_model_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_models_org", "ai_models", ["org_id"])
    op.create_index("ix_ai_models_provider", "ai_models", ["provider"])
    op.create_index("ix_ai_models_version", "ai_models", ["version"])

    # ── ai_agents ──────────────────────────────────────────────────────────
    op.create_table(
        "ai_agents",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("model_id", sa.Uuid(), sa.ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True),
        sa.Column("autonomy_level", sa.String(32), server_default="l1_recommend", nullable=False),  # l0_observe, l1_recommend, l2_execute_low_risk, l3_execute_approved, l4_conditional_autonomous, l5_restricted_full
        sa.Column("risk_level", sa.String(32), server_default="medium", nullable=False),
        sa.Column("permissions", sa.Text(), nullable=True),  # JSON comma-separated
        sa.Column("authorized_tools", sa.Text(), nullable=True),  # JSON
        sa.Column("authorized_environments", sa.Text(), nullable=True),  # JSON
        sa.Column("authorized_data", sa.Text(), nullable=True),  # JSON
        sa.Column("authorized_workflows", sa.Text(), nullable=True),  # JSON
        sa.Column("evaluation_status", sa.String(32), server_default="not_evaluated", nullable=False),
        sa.Column("approval_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("approval_by", sa.String(128), nullable=True),
        sa.Column("approval_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_reason", sa.Text(), nullable=True),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_agents_org", "ai_agents", ["org_id"])
    op.create_index("ix_ai_agents_model", "ai_agents", ["model_id"])

    # ── ai_prompts ──────────────────────────────────────────────────────────
    op.create_table(
        "ai_prompts",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("prompt_type", sa.String(32), server_default="system", nullable=False),  # system, agent, evaluation, workflow
        sa.Column("model_compatibility", sa.Text(), nullable=True),  # JSON
        sa.Column("risk_level", sa.String(32), server_default="medium", nullable=False),
        sa.Column("approval_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_reason", sa.Text(), nullable=True),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.String(64), server_default="1.0.0", nullable=False),
        sa.Column("changes", sa.Text(), nullable=True),
        sa.Column("evaluation_status", sa.String(32), server_default="not_evaluated", nullable=False),
        sa.Column("last_evaluated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deployment_status", sa.String(32), server_default="not_deployed", nullable=False),  # not_deployed, deployed, deprecated, retired
        sa.Column("depends_on_prompt_id", sa.Uuid(), sa.ForeignKey("ai_prompts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_prompts_org", "ai_prompts", ["org_id"])
    op.create_index("ix_ai_prompts_type", "ai_prompts", ["prompt_type"])
    op.create_index("ix_ai_prompts_dep", "ai_prompts", ["depends_on_prompt_id"])

    # ── ai_tools ────────────────────────────────────────────────────────────
    op.create_table(
        "ai_tools",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tool_type", sa.String(64), nullable=True),  # analysis, retrieval, transformation, generation, embedding, classification, etc.
        sa.Column("permissions", sa.Text(), nullable=True),  # JSON
        sa.Column("data_access", sa.Text(), nullable=True),  # JSON
        sa.Column("input_schema", sa.Text(), nullable=True),
        sa.Column("output_schema", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(32), server_default="medium", nullable=False),
        sa.Column("approval_status", sa.String(32), server_default="pending", nullable=False),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_reason", sa.Text(), nullable=True),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("autonomy_level", sa.String(32), server_default="l1_recommend", nullable=False),  # l0_observe through l5_restricted_full
        sa.Column("high_risk_action", sa.Boolean(), server_default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_tools_org", "ai_tools", ["org_id"])

    # ── ai_policies ──────────────────────────────────────────────────────────
    op.create_table(
        "ai_policies",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("policy_type", sa.String(32), nullable=False),  # model, prompt, agent, tool, data, provider, region, autonomy, action
        sa.Column("effect", sa.String(32), server_default="allow", nullable=False),  # allow, deny, require_approval, degrade, log_only
        sa.Column("severity", sa.String(32), server_default="medium", nullable=False),  # low, medium, high, critical
        sa.Column("conditions", sa.Text(), nullable=True),  # JSON
        sa.Column("actions", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default=0, nullable=False),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),  # active, inactive, deprecated
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expiration_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner", sa.String(128), nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_reason", sa.Text(), nullable=True),
        sa.Column("tags", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_policies_org", "ai_policies", ["org_id"])
    op.create_index("ix_ai_policies_type", "ai_policies", ["policy_type"])

    # ── ai_policy_decisions ────────────────────────────────────────────────
    op.create_table(
        "ai_policy_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("policy_id", sa.Uuid(), sa.ForeignKey("ai_policies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_type", sa.String(32), nullable=True),  # model, agent, prompt, tool
        sa.Column("decision", sa.String(32), nullable=False),  # allow, deny, require_approval, degrade, log_only
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),  # JSON
        sa.Column("context", sa.Text(), nullable=True),  # JSON
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_by", sa.String(128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_policy_decisions_policy", "ai_policy_decisions", ["policy_id"])
    op.create_index("ix_policy_decisions_asset", "ai_policy_decisions", ["asset_id"])

    # ── ai_evaluations ──────────────────────────────────────────────────────
    op.create_table(
        "ai_evaluations",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),  # model, agent, prompt, tool
        sa.Column("evaluation_name", sa.String(256), nullable=False),
        sa.Column("evaluation_type", sa.String(32), nullable=True),  # quality, safety, security, groundedness, citation_accuracy, reliability, latency, cost
        sa.Column("status", sa.String(32), server_default="not_evaluated", nullable=False),  # not_evaluated, pending, passed, failed, expired
        sa.Column("metrics", sa.Text(), nullable=True),  # JSON
        sa.Column("thresholds", sa.Text(), nullable=True),  # JSON
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_by", sa.String(128), nullable=True),
        sa.Column("passed", sa.Boolean, server_default=False, nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("trigger", sa.String(64), nullable=True),  # manual, regression_check, approval_gate, drift_detect, mandatory
        sa.Column("related_asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("trigger_asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_evaluations_asset", "ai_evaluations", ["asset_id"])
    op.create_index("ix_ai_evaluations_type", "ai_evaluations", ["asset_type"])

    # ── ai_risk_assessments ────────────────────────────────────────────────
    op.create_table(
        "ai_risk_assessments",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),  # model, agent, prompt, tool
        sa.Column("risk_level", sa.String(32), server_default="medium", nullable=False),
        sa.Column("risk_factors", sa.Text(), nullable=True),  # JSON
        sa.Column("overall_score", sa.Float(), server_default=0.5, nullable=False),
        sa.Column("likelihood", sa.String(32), server_default="medium", nullable=False),
        sa.Column("impact", sa.String(32), server_default="medium", nullable=False),
        sa.Column("affected_areas", sa.Text(), nullable=True),  # JSON
        sa.Column("mitigation_plan", sa.Text(), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessed_by", sa.String(128), nullable=True),
        sa.Column("next_review", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger", sa.String(64), nullable=True),  # manual, drift_detect, approval_gate, incident, mandatory
        sa.Column("trigger_asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_risk_assessments_asset", "ai_risk_assessments", ["asset_id"])

    # ── ai_exceptions ────────────────────────────────────────────────────────
    op.create_table(
        "ai_exceptions",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("asset_type", sa.String(32), nullable=True),
        sa.Column("policy_id", sa.Uuid(), sa.ForeignKey("ai_policies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("risk", sa.String(32), server_default="medium", nullable=False),
        sa.Column("compensating_controls", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_exceptions_asset", "ai_exceptions", ["asset_id"])

    # ── ai_incidents ────────────────────────────────────────────────────────
    op.create_table(
        "ai_incidents",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_type", sa.String(32), nullable=True),  # model, agent, prompt, tool
        sa.Column("incident_id", sa.String(64), nullable=True),
        sa.Column("input_category", sa.String(64), nullable=True),  # prompt_injection, data_leakage, unsafe_code, unauthorized_action, excessive_tool_use, malicious_document, malicious_repository, unsafe_autonomous_behavior
        sa.Column("action", sa.String(128), nullable=True),
        sa.Column("impact", sa.String(32), server_default="medium", nullable=False),  # low, medium, high, critical
        sa.Column("evidence", sa.Text(), nullable=True),  # JSON
        sa.Column("containment", sa.String(32), server_default="none", nullable=False),  # none, isolate, restrict, disable
        sa.Column("remediation", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(128), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_incidents_org", "ai_incidents", ["org_id"])
    op.create_index("ix_ai_incidents_asset", "ai_incidents", ["asset_id"])

    # ── ai_feedback ──────────────────────────────────────────────────────────
    op.create_table(
        "ai_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_type", sa.String(32), nullable=True),
        sa.Column("user_id", sa.String(128), nullable=True),
        sa.Column("feedback_type", sa.String(32), nullable=True),  # quality_rating, issue_category, correction, feature_request
        sa.Column("rating", sa.Integer(), nullable=True),  # 1-5
        sa.Column("issue_category", sa.String(128), nullable=True),
        sa.Column("correction", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("triggered_reeval", sa.Boolean, server_default=False, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_feedback_asset", "ai_feedback", ["asset_id"])

    # ── ai_governance_reviews ──────────────────────────────────────────────
    op.create_table(
        "ai_governance_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_type", sa.String(32), nullable=True),  # model, agent, prompt, tool
        sa.Column("review_type", sa.String(32), nullable=False),  # periodic, approval_expiry, drift_detect, incident_followup, mandatory
        sa.Column("status", sa.String(32), server_default="pending", nullable=False),  # pending, passed, failed, requires_action
        sa.Column("evaluations_covered", sa.Text(), nullable=True),  # JSON asset IDs
        sa.Column("reviews_covered", sa.Text(), nullable=True),  # JSON asset IDs
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(32), server_default="pending", nullable=False),  # pass, fail, restrict, retire
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_governance_reviews_org", "ai_governance_reviews", ["org_id"])
    op.create_index("ix_ai_governance_reviews_asset", "ai_governance_reviews", ["asset_id"])

    # ── ai_lifecycle_events ────────────────────────────────────────────────
    op.create_table(
        "ai_lifecycle_events",
        sa.Column("id", sa.Uuid(), primary_key=True, default=sa.uuid_generate_v4()),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("asset_type", sa.String(32), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),  # ai_asset_created, ai_asset_updated, ai_approval_granted, ai_approval_expired, ai_policy_denied, ai_policy_violation, ai_evaluation_failed, ai_regression_detected, ai_incident_created, ai_asset_restricted, ai_asset_disabled, ai_model_retired
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(128), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("related_asset_id", sa.Uuid(), sa.ForeignKey("ai_assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),  # JSON
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_lifecycle_events_org", "ai_lifecycle_events", ["org_id"])
    op.create_index("ix_ai_lifecycle_events_asset", "ai_lifecycle_events", ["asset_id"])


def downgrade() -> None:
    # Drop in reverse order to maintain foreign key integrity
    op.drop_table("ai_lifecycle_events")
    op.drop_table("ai_governance_reviews")
    op.drop_table("ai_feedback")
    op.drop_table("ai_incidents")
    op.drop_table("ai_exceptions")
    op.drop_table("ai_risk_assessments")
    op.drop_table("ai_evaluations")
    op.drop_table("ai_policy_decisions")
    op.drop_table("ai_policies")
    op.drop_table("ai_tools")
    op.drop_index("ix_ai_prompts_dep", table_name="ai_prompts")
    op.drop_index("ix_ai_prompts_type", table_name="ai_prompts")
    op.drop_index("ix_ai_prompts_org", table_name="ai_prompts")
    op.drop_table("ai_prompts")
    op.drop_index("ix_ai_agents_model", table_name="ai_agents")
    op.drop_index("ix_ai_agents_org", table_name="ai_agents")
    op.drop_table("ai_agents")
    op.drop_index("ix_ai_models_version", table_name="ai_models")
    op.drop_index("ix_ai_models_provider", table_name="ai_models")
    op.drop_index("ix_ai_models_org", table_name="ai_models")
    op.drop_table("ai_models")
    op.drop_index("ix_asset_versions_asset", table_name="ai_asset_versions")
    op.drop_table("ai_asset_versions")
    op.drop_index("ix_ai_assets_status", table_name="ai_assets")
    op.drop_index("ix_ai_assets_type", table_name="ai_assets")
    op.drop_index("ix_ai_assets_org", table_name="ai_assets")
    op.drop_table("ai_assets")