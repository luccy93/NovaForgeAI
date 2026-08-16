"""Site Reliability Engineering (Volume 35) - schema migration.

Revision ID: 0003_sre
Revises: 0002_automation
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_sre"
down_revision = "0002_automation"
branch_labels = None
depends_on = None


def _json_type():
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else "postgresql"
    return JSONB if dialect == "postgresql" else sa.JSON


def upgrade() -> None:
    json_type = _json_type()

    # ------------------------------------------------------------ services
    op.create_table(
        "sre_services",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("service_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, default=""),
        sa.Column("owner", sa.String(128), default=""),
        sa.Column("team", sa.String(128), default=""),
        sa.Column("tier", sa.String(16), default="tier1", index=True),
        sa.Column("criticality", sa.String(16), default="high"),
        sa.Column("deployment_strategy", sa.String(24), default="rolling"),
        sa.Column("scaling_strategy", sa.String(128), default=""),
        sa.Column("backup_strategy", sa.String(255), default=""),
        sa.Column("rto_minutes", sa.Integer, default=60),
        sa.Column("rpo_minutes", sa.Integer, default=60),
        sa.Column("runbook_id", sa.String(64), default=""),
        sa.Column("on_call", sa.String(255), default=""),
        sa.Column("status", sa.String(24), default="operational", index=True),
        sa.Column("metadata_json", json_type, default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sre_services_tier", "sre_services", ["tier"])

    op.create_table(
        "sre_service_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("service_id", sa.String(96), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False, default=1),
        sa.Column("spec", json_type, default=dict),
        sa.Column("created_by", sa.String(128), default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sre_service_dependencies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("service_id", sa.String(96), nullable=False, index=True),
        sa.Column("depends_on", sa.String(96), nullable=False, index=True),
        sa.Column("kind", sa.String(32), default="service"),
        sa.Column("critical", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ---------------------------------------------------------------- SLOs
    op.create_table(
        "sre_slos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("slo_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("service_id", sa.String(96), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, default=""),
        sa.Column("sli_type", sa.String(32), nullable=False),
        sa.Column("target", sa.Float, nullable=False),
        sa.Column("window", sa.String(16), default="monthly"),
        sa.Column("measurement", sa.String(255), default=""),
        sa.Column("query", sa.Text, default=""),
        sa.Column("owner", sa.String(128), default=""),
        sa.Column("severity", sa.String(8), default="SEV2"),
        sa.Column("status", sa.String(16), default="active", index=True),
        sa.Column("version", sa.Integer, default=1),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sre_sli_measurements",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("slo_id", sa.String(96), nullable=False, index=True),
        sa.Column("service_id", sa.String(96), nullable=False, index=True),
        sa.Column("sli_type", sa.String(32), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("bucket_seconds", sa.Integer, default=60),
        sa.Column("good", sa.Float, default=0.0),
        sa.Column("total", sa.Float, default=0.0),
        sa.Column("value", sa.Float, default=0.0),
        sa.Column("region", sa.String(32), default="", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sre_error_budgets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("slo_id", sa.String(96), nullable=False, index=True),
        sa.Column("service_id", sa.String(96), nullable=False, index=True),
        sa.Column("window", sa.String(16), default="monthly"),
        sa.Column("allowed_failure", sa.Float, nullable=False),
        sa.Column("actual_failure", sa.Float, nullable=False),
        sa.Column("remaining_budget", sa.Float, nullable=False),
        sa.Column("consumed_percent", sa.Float, default=0.0),
        sa.Column("burn_rate", sa.Float, default=0.0),
        sa.Column("status", sa.String(16), default="healthy"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # --------------------------------------------------------------- alerts
    op.create_table(
        "sre_alerts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("alert_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("rule_name", sa.String(255), nullable=False),
        sa.Column("severity", sa.String(8), default="SEV3"),
        sa.Column("service_id", sa.String(96), default="", index=True),
        sa.Column("region", sa.String(32), default=""),
        sa.Column("message", sa.Text, default=""),
        sa.Column("status", sa.String(24), default="firing", index=True),
        sa.Column("metadata_json", json_type, default=dict),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ------------------------------------------------------------ incidents
    op.create_table(
        "sre_incidents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("incident_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("organization_id", sa.String(64), default="", index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, default=""),
        sa.Column("severity", sa.String(8), default="SEV2", index=True),
        sa.Column("status", sa.String(24), default="detected", index=True),
        sa.Column("service_id", sa.String(96), default="", index=True),
        sa.Column("region", sa.String(32), default=""),
        sa.Column("commander", sa.String(128), default=""),
        sa.Column("impact", json_type, default=dict),
        sa.Column("root_cause", sa.Text, default=""),
        sa.Column("detection", sa.String(64), default="alert"),
        sa.Column("related_deployments", json_type, default=list),
        sa.Column("related_changes", json_type, default=list),
        sa.Column("related_alerts", json_type, default=list),
        sa.Column("postmortem_id", sa.String(64), default=""),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mitigated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sre_incident_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("incident_id", sa.String(96), nullable=False, index=True),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("actor", sa.String(128), default="system"),
        sa.Column("message", sa.Text, default=""),
        sa.Column("metadata_json", json_type, default=dict),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    op.create_table(
        "sre_incident_responders",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("incident_id", sa.String(96), nullable=False, index=True),
        sa.Column("role", sa.String(48), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ---------------------------------------------------------- postmortems
    op.create_table(
        "sre_postmortems",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("postmortem_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("incident_id", sa.String(96), nullable=False, index=True),
        sa.Column("summary", sa.Text, default=""),
        sa.Column("impact", sa.Text, default=""),
        sa.Column("timeline", json_type, default=list),
        sa.Column("root_cause", sa.Text, default=""),
        sa.Column("contributing_factors", json_type, default=list),
        sa.Column("detection", sa.Text, default=""),
        sa.Column("response", sa.Text, default=""),
        sa.Column("what_went_well", json_type, default=list),
        sa.Column("what_went_wrong", json_type, default=list),
        sa.Column("status", sa.String(24), default="draft", index=True),
        sa.Column("created_by", sa.String(128), default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sre_corrective_actions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("action_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("incident_id", sa.String(96), default="", index=True),
        sa.Column("postmortem_id", sa.String(96), default="", index=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("owner", sa.String(128), default=""),
        sa.Column("priority", sa.String(16), default="medium"),
        sa.Column("status", sa.String(24), default="open", index=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification", sa.Text, default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------- runbooks
    op.create_table(
        "sre_runbooks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("runbook_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("service_id", sa.String(96), default="", index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("purpose", sa.Text, default=""),
        sa.Column("symptoms", json_type, default=list),
        sa.Column("impact", sa.Text, default=""),
        sa.Column("diagnosis", json_type, default=list),
        sa.Column("commands", json_type, default=list),
        sa.Column("checks", json_type, default=list),
        sa.Column("mitigation", json_type, default=list),
        sa.Column("rollback", json_type, default=list),
        sa.Column("recovery", json_type, default=list),
        sa.Column("escalation", json_type, default=list),
        sa.Column("post_incident", json_type, default=list),
        sa.Column("owner", sa.String(128), default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -------------------------------------------------- maintenance windows
    op.create_table(
        "sre_maintenance_windows",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("maintenance_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("organization_id", sa.String(64), default="", index=True),
        sa.Column("scope", sa.String(24), default="service"),
        sa.Column("target", sa.String(96), default=""),
        sa.Column("description", sa.Text, default=""),
        sa.Column("status", sa.String(24), default="scheduled", index=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -------------------------------------------------------------- regions
    op.create_table(
        "sre_regions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("region", sa.String(32), nullable=False, unique=True, index=True),
        sa.Column("mode", sa.String(24), default="active-active"),
        sa.Column("status", sa.String(24), default="operational", index=True),
        sa.Column("capacity_percent", sa.Float, default=50.0),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sre_region_health",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("region", sa.String(32), nullable=False, index=True),
        sa.Column("availability", sa.Float, default=1.0),
        sa.Column("latency_ms", sa.Float, default=0.0),
        sa.Column("error_rate", sa.Float, default=0.0),
        sa.Column("capacity_percent", sa.Float, default=0.0),
        sa.Column("dependency_health", json_type, default=dict),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # ------------------------------------------------------------- capacity
    op.create_table(
        "sre_capacity_metrics",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("service_id", sa.String(96), default="", index=True),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("limit", sa.Float, default=100.0),
        sa.Column("unit", sa.String(16), default="percent"),
        sa.Column("region", sa.String(32), default=""),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # --------------------------------------------------------------- backups
    op.create_table(
        "sre_backup_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("backup_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("region", sa.String(32), default=""),
        sa.Column("kind", sa.String(24), default="full"),
        sa.Column("status", sa.String(24), default="pending", index=True),
        sa.Column("size_bytes", sa.BigInteger, default=0),
        sa.Column("verified", sa.Boolean, default=False),
        sa.Column("error", sa.Text, default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sre_restore_tests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("test_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("backup_id", sa.String(96), default="", index=True),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), default="pending", index=True),
        sa.Column("integrity", sa.Boolean, default=False),
        sa.Column("completeness", sa.Boolean, default=False),
        sa.Column("consistency", sa.Boolean, default=False),
        sa.Column("app_compatible", sa.Boolean, default=False),
        sa.Column("duration_seconds", sa.Integer, default=0),
        sa.Column("notes", sa.Text, default=""),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sre_failover_tests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("test_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(32), default=""),
        sa.Column("status", sa.String(24), default="pending", index=True),
        sa.Column("rto_achieved_minutes", sa.Integer, default=0),
        sa.Column("data_loss_minutes", sa.Integer, default=0),
        sa.Column("passed", sa.Boolean, default=False),
        sa.Column("notes", sa.Text, default=""),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ---------------------------------------------------------------- chaos
    op.create_table(
        "sre_chaos_experiments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("experiment_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("organization_id", sa.String(64), default="", index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("experiment_type", sa.String(64), nullable=False),
        sa.Column("target", sa.String(96), default=""),
        sa.Column("scope", sa.String(255), default=""),
        sa.Column("blast_radius", sa.String(64), default="test"),
        sa.Column("owner", sa.String(128), default=""),
        sa.Column("abort_condition", sa.Text, default=""),
        sa.Column("expected_result", sa.Text, default=""),
        sa.Column("actual_result", sa.Text, default=""),
        sa.Column("status", sa.String(24), default="pending", index=True),
        sa.Column("duration_seconds", sa.Integer, default=30),
        sa.Column("recovery_seconds", sa.Float, default=0.0),
        sa.Column("passed", sa.Boolean, default=False),
        sa.Column("created_by", sa.String(128), default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --------------------------------------------------- dependency health
    op.create_table(
        "sre_dependency_health",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("dependency", sa.String(96), nullable=False, index=True),
        sa.Column("kind", sa.String(32), default="external"),
        sa.Column("status", sa.String(24), default="unknown", index=True),
        sa.Column("latency_ms", sa.Float, default=0.0),
        sa.Column("error_rate", sa.Float, default=0.0),
        sa.Column("metadata_json", json_type, default=dict),
        sa.Column("last_outage_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # --------------------------------------------------- status components
    op.create_table(
        "sre_status_components",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("component_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("service_id", sa.String(96), default="", index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, default=""),
        sa.Column("status", sa.String(24), default="operational", index=True),
        sa.Column("region", sa.String(32), default=""),
        sa.Column("public", sa.Boolean, default=False),
        sa.Column("history", json_type, default=list),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # -------------------------------------------------------------- dead letter
    op.create_table(
        "sre_dead_letter_entries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("entry_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("event_id", sa.String(96), default="", index=True),
        sa.Column("source", sa.String(96), default=""),
        sa.Column("queue", sa.String(96), nullable=False, index=True),
        sa.Column("error", sa.Text, default=""),
        sa.Column("attempts", sa.Integer, default=0),
        sa.Column("payload_reference", sa.String(255), default=""),
        sa.Column("correlation_id", sa.String(96), default="", index=True),
        sa.Column("status", sa.String(24), default="open", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------------------ deployments
    op.create_table(
        "sre_deployments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("deployment_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("service_id", sa.String(96), nullable=False, index=True),
        sa.Column("version", sa.String(64), default=""),
        sa.Column("strategy", sa.String(24), default="rolling"),
        sa.Column("status", sa.String(24), default="in_progress", index=True),
        sa.Column("region", sa.String(32), default=""),
        sa.Column("commit", sa.String(64), default=""),
        sa.Column("environment", sa.String(24), default="production"),
        sa.Column("duration_seconds", sa.Integer, default=0),
        sa.Column("error_rate_after", sa.Float, default=0.0),
        sa.Column("latency_after_ms", sa.Float, default=0.0),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sre_canary_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("canary_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("deployment_id", sa.String(96), default="", index=True),
        sa.Column("service_id", sa.String(96), nullable=False, index=True),
        sa.Column("status", sa.String(24), default="in_progress", index=True),
        sa.Column("baseline_error_rate", sa.Float, default=0.0),
        sa.Column("canary_error_rate", sa.Float, default=0.0),
        sa.Column("baseline_latency_ms", sa.Float, default=0.0),
        sa.Column("canary_latency_ms", sa.Float, default=0.0),
        sa.Column("error_rate_threshold", sa.Float, default=0.5),
        sa.Column("latency_threshold_multiplier", sa.Float, default=1.5),
        sa.Column("aborted", sa.Boolean, default=False),
        sa.Column("reason", sa.Text, default=""),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ----------------------------------------------------------- certificates
    op.create_table(
        "sre_certificates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("certificate_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False, index=True),
        sa.Column("issuer", sa.String(255), default=""),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("status", sa.String(24), default="valid", index=True),
        sa.Column("auto_renew", sa.Boolean, default=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ------------------------------------------------- remediation actions
    op.create_table(
        "sre_remediation_actions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("action_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target", sa.String(128), default=""),
        sa.Column("reason", sa.Text, default=""),
        sa.Column("evidence", json_type, default=list),
        sa.Column("policy", sa.String(64), default=""),
        sa.Column("authorized", sa.Boolean, default=False),
        sa.Column("requires_approval", sa.Boolean, default=False),
        sa.Column("approved_by", sa.String(128), default=""),
        sa.Column("result", sa.String(24), default="pending", index=True),
        sa.Column("rollback", sa.Text, default=""),
        sa.Column("attempt", sa.Integer, default=1),
        sa.Column("max_attempts", sa.Integer, default=1),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --------------------------------------------------------------- reports
    op.create_table(
        "sre_reports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("report_id", sa.String(96), nullable=False, unique=True, index=True),
        sa.Column("kind", sa.String(32), nullable=False, index=True),
        sa.Column("title", sa.String(255), default=""),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", json_type, default=dict),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    tables = [
        "sre_reports",
        "sre_remediation_actions",
        "sre_certificates",
        "sre_canary_runs",
        "sre_deployments",
        "sre_dead_letter_entries",
        "sre_status_components",
        "sre_dependency_health",
        "sre_chaos_experiments",
        "sre_failover_tests",
        "sre_restore_tests",
        "sre_backup_jobs",
        "sre_capacity_metrics",
        "sre_region_health",
        "sre_regions",
        "sre_maintenance_windows",
        "sre_runbooks",
        "sre_corrective_actions",
        "sre_postmortems",
        "sre_incident_responders",
        "sre_incident_events",
        "sre_incidents",
        "sre_alerts",
        "sre_error_budgets",
        "sre_sli_measurements",
        "sre_slos",
        "sre_service_dependencies",
        "sre_service_versions",
        "sre_services",
    ]
    for table in tables:
        op.drop_table(table)
