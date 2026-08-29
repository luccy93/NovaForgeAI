"""Event bus — pub/sub, async events, persistence, replay, ordering."""

import json
import uuid
import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from app.core.config import settings
from app.core.redis import get_redis


class EventType(str, Enum):
    repository_created = "repository.created"
    repository_updated = "repository.updated"
    repository_deleted = "repository.deleted"
    repository_imported = "repository.imported"
    organization_created = "organization.created"
    organization_updated = "organization.updated"
    organization_deleted = "organization.deleted"
    user_created = "user.created"
    user_updated = "user.updated"
    user_deleted = "user.deleted"
    agent_run_completed = "agent.run.completed"
    agent_run_failed = "agent.run.failed"
    pipeline_completed = "pipeline.completed"
    deployment_started = "deployment.started"
    deployment_completed = "deployment.completed"
    deployment_failed = "deployment.failed"
    security_alert = "security.alert"
    security_scan_completed = "security.scan.completed"
    billing_subscription_changed = "billing.subscription.changed"
    billing_payment_failed = "billing.payment.failed"
    notification_sent = "notification.sent"
    webhook_delivered = "webhook.delivered"
    webhook_failed = "webhook.failed"
    plugin_installed = "plugin.installed"
    plugin_uninstalled = "plugin.uninstalled"
    plugin_updated = "plugin.updated"

    # Marketplace events (Volume 44) — idempotent lifecycle events.
    marketplace_package_published = "marketplace.package.published"
    marketplace_package_updated = "marketplace.package.updated"
    marketplace_package_installed = "marketplace.package.installed"
    marketplace_package_uninstalled = "marketplace.package.uninstalled"
    marketplace_package_suspended = "marketplace.package.suspended"
    marketplace_package_reported = "marketplace.package.reported"
    marketplace_package_security_issue = "marketplace.package.security_issue"
    marketplace_package_deprecated = "marketplace.package.deprecated"
    marketplace_package_retired = "marketplace.package.retired"
    # Volume 55 ecosystem extensions
    marketplace_package_created = "marketplace.package.created"
    marketplace_version_published = "marketplace.version.published"
    marketplace_scan_started = "marketplace.scan.started"
    marketplace_scan_completed = "marketplace.scan.completed"
    marketplace_package_approved = "marketplace.package.approved"
    marketplace_package_rejected = "marketplace.package.rejected"
    marketplace_package_install_failed = "marketplace.package.install_failed"
    marketplace_package_updated_v2 = "marketplace.package.updated_v2"
    marketplace_package_rolled_back = "marketplace.package.rolled_back"

    # SRE events (Volume 35) — idempotent operational events.
    service_degraded = "sre.service.degraded"
    service_recovered = "sre.service.recovered"
    slo_violation = "sre.slo.violation"
    error_budget_burning = "sre.error_budget.burning"
    incident_created = "sre.incident.created"
    incident_updated = "sre.incident.updated"
    incident_resolved = "sre.incident.resolved"
    rollback_triggered = "sre.rollback.triggered"
    dependency_outage = "sre.dependency.outage"
    region_degraded = "sre.region.degraded"
    backup_failed = "sre.backup.failed"
    restore_failed = "sre.restore.failed"
    capacity_warning = "sre.capacity.warning"
    certificate_expiring = "sre.certificate.expiring"
    sre_alert_fired = "sre.alert.fired"
    remediation_executed = "sre.remediation.executed"
    canary_aborted = "sre.canary.aborted"

    # Autonomous Software-Engineering events (Volume 45)
    automation_task_created = "automation.task.created"
    automation_task_started = "automation.task.started"
    automation_task_completed = "automation.task.completed"
    automation_task_failed = "automation.task.failed"
    automation_task_cancelled = "automation.task.cancelled"
    automation_plan_created = "automation.plan.created"
    automation_plan_approved = "automation.plan.approved"
    automation_approval_required = "automation.approval.required"
    automation_patch_generated = "automation.patch.generated"
    automation_patch_validated = "automation.patch.validated"
    automation_tests_started = "automation.tests.started"
    automation_tests_passed = "automation.tests.passed"
    automation_tests_failed = "automation.tests.failed"
    automation_review_completed = "automation.review.completed"
    automation_security_gate_failed = "automation.security.gate_failed"
    automation_deployment_started = "automation.deployment.started"
    automation_deployment_completed = "automation.deployment.completed"
    automation_deployment_rollback = "automation.deployment.rollback"
    automation_budget_exceeded = "automation.budget.exceeded"

    # Software Delivery Platform events (Volume 46)
    delivery_pipeline_created = "delivery.pipeline.created"
    delivery_pipeline_run_started = "delivery.pipeline.run_started"
    delivery_pipeline_run_completed = "delivery.pipeline.run_completed"
    delivery_pipeline_run_failed = "delivery.pipeline.run_failed"
    delivery_job_started = "delivery.job.started"
    delivery_job_completed = "delivery.job.completed"
    delivery_job_failed = "delivery.job.failed"
    delivery_runner_registered = "delivery.runner.registered"
    delivery_runner_quarantined = "delivery.runner.quarantined"
    delivery_artifact_published = "delivery.artifact.published"
    delivery_artifact_signed = "delivery.artifact.signed"
    delivery_artifact_promoted = "delivery.artifact.promoted"
    delivery_deployment_started = "delivery.deployment.started"
    delivery_deployment_completed = "delivery.deployment.completed"
    delivery_deployment_failed = "delivery.deployment.failed"
    delivery_deployment_rollback = "delivery.deployment.rollback"
    delivery_release_created = "delivery.release.created"
    delivery_release_promoted = "delivery.release.promoted"
    delivery_release_finalized = "delivery.release.finalized"
    delivery_preview_created = "delivery.preview.created"
    delivery_preview_destroyed = "delivery.preview.destroyed"
    delivery_approval_requested = "delivery.approval.requested"
    delivery_approval_granted = "delivery.approval.granted"
    delivery_approval_rejected = "delivery.approval.rejected"
    delivery_environment_frozen = "delivery.environment.frozen"
    delivery_environment_locked = "delivery.environment.locked"
    delivery_rollout_started = "delivery.rollout.started"
    delivery_rollout_expanded = "delivery.rollout.expanded"
    delivery_rollout_aborted = "delivery.rollout.aborted"

    # Unified DevSecOps Security Platform events (Volume 47)
    security_platform_scan_started = "security.platform.scan_started"
    security_platform_scan_completed = "security.platform.scan_completed"
    security_platform_finding_created = "security.platform.finding_created"
    security_platform_finding_updated = "security.platform.finding_updated"
    security_platform_critical_finding = "security.platform.critical_finding"
    security_platform_secret_detected = "security.platform.secret_detected"
    security_platform_artifact_blocked = "security.platform.artifact_blocked"
    security_platform_gate_failed = "security.platform.gate_failed"
    security_platform_risk_accepted = "security.platform.risk_accepted"
    security_platform_fix_started = "security.platform.fix_started"
    security_platform_fix_verified = "security.platform.fix_verified"
    security_platform_incident_created = "security.platform.incident_created"
    security_platform_policy_evaluated = "security.platform.policy_evaluated"
    security_platform_dependency_vulnerability = "security.platform.dependency_vulnerability"
    security_platform_sbom_generated = "security.platform.sbom_generated"
    security_platform_supply_chain_violation = "security.platform.supply_chain_violation"
    security_platform_container_vulnerability = "security.platform.container_vulnerability"

    # AI Software Quality Engine events (Volume 48)
    quality_review_started = "quality.review.started"
    quality_review_completed = "quality.review.completed"
    quality_review_failed = "quality.review.failed"
    quality_review_cancelled = "quality.review.cancelled"
    quality_finding_created = "quality.finding.created"
    quality_finding_updated = "quality.finding.updated"
    quality_finding_acknowledged = "quality.finding.acknowledged"
    quality_finding_fixed = "quality.finding.fixed"
    quality_gate_passed = "quality.gate.passed"
    quality_gate_failed = "quality.gate.failed"
    quality_gate_blocked = "quality.gate.blocked"
    quality_remediation_proposed = "quality.remediation.proposed"
    quality_remediation_verified = "quality.remediation.verified"
    quality_baseline_created = "quality.baseline.created"
    quality_test_generated = "quality.test.generated"

    # Incident Response Platform events (Volume 49)
    incident_detected = "incident.detected"
    incident_acknowledged = "incident.acknowledged"
    incident_triaged = "incident.triaged"
    incident_investigating = "incident.investigating"
    incident_mitigating = "incident.mitigating"
    incident_monitoring = "incident.monitoring"
    incident_platform_resolved = "incident.resolved"
    incident_postmortem = "incident.postmortem"
    incident_closed = "incident.closed"
    incident_escalated = "incident.escalated"
    incident_action_approved = "incident.action.approved"
    incident_action_executed = "incident.action.executed"
    incident_runbook_executed = "incident.runbook.executed"
    incident_anomaly_detected = "incident.anomaly.detected"
    incident_alert_ingested = "incident.alert.ingested"

    # Production-Grade Billing Platform events (Volume 53)
    billing_plan_created = "billing.plan.created"
    billing_plan_updated = "billing.plan.updated"
    billing_plan_deleted = "billing.plan.deleted"
    billing_subscription_created = "billing.subscription.created"
    billing_subscription_updated = "billing.subscription.updated"
    billing_subscription_canceled = "billing.subscription.canceled"
    billing_subscription_reactivated = "billing.subscription.reactivated"
    billing_invoice_created = "billing.invoice.created"
    billing_invoice_finalized = "billing.invoice.finalized"
    billing_invoice_paid = "billing.invoice.paid"
    billing_invoice_voided = "billing.invoice.voided"
    billing_payment_succeeded = "billing.payment.succeeded"
    billing_payment_failed_v2 = "billing.payment.failed_v2"
    billing_payment_refunded = "billing.payment.refunded"
    billing_usage_recorded = "billing.usage.recorded"
    billing_usage_threshold = "billing.usage.threshold"
    billing_credit_granted = "billing.credit.granted"
    billing_credit_deducted = "billing.credit.deducted"
    billing_coupon_created = "billing.coupon.created"
    billing_coupon_applied = "billing.coupon.applied"
    billing_budget_created = "billing.budget.created"
    billing_budget_warning = "billing.budget.warning"
    billing_budget_exceeded = "billing.budget.exceeded"
    billing_dunning_started = "billing.dunning.started"
    billing_dunning_action = "billing.dunning.action"
    billing_reconciliation_created = "billing.reconciliation.created"
    billing_marketplace_purchase = "billing.marketplace.purchase"

    # Unified Analytics Platform events (Volume 50)
    analytics_event_ingested = "analytics.event.ingested"
    analytics_event_normalized = "analytics.event.normalized"
    analytics_event_deduplicated = "analytics.event.deduplicated"
    analytics_event_validated = "analytics.event.validated"
    analytics_metric_recorded = "analytics.metric.recorded"
    analytics_cost_recorded = "analytics.cost.recorded"
    analytics_budget_created = "analytics.budget.created"
    analytics_budget_warning = "analytics.budget.warning"
    analytics_budget_exceeded = "analytics.budget.exceeded"
    analytics_alert_created = "analytics.alert.created"
    analytics_alert_triggered = "analytics.alert.triggered"
    analytics_report_generated = "analytics.report.generated"
    analytics_forecast_created = "analytics.forecast.created"
    analytics_recommendation_generated = "analytics.recommendation.generated"
    analytics_anomaly_detected = "analytics.anomaly.detected"
    analytics_slo_breach = "analytics.slo.breach"
    analytics_dora_computed = "analytics.dora.computed"
    analytics_ai_call_recorded = "analytics.ai.call.recorded"
    analytics_agent_run_recorded = "analytics.agent.run.recorded"
    analytics_quality_issue_detected = "analytics.quality.issue.detected"
    analytics_security_finding_recorded = "analytics.security.finding.recorded"
    analytics_marketplace_event_recorded = "analytics.marketplace.event.recorded"
    analytics_insights_generated = "analytics.insights.generated"
    analytics_dashboard_accessed = "analytics.dashboard.accessed"

    # Knowledge Graph Platform (Volume 51)
    knowledge_graph_entity_created = "knowledge_graph_entity_created"
    knowledge_graph_entity_updated = "knowledge_graph_entity_updated"
    knowledge_graph_entity_deleted = "knowledge_graph_entity_deleted"
    knowledge_graph_entity_merged = "knowledge_graph_entity_merged"
    knowledge_graph_relationship_created = "knowledge_graph_relationship_created"
    knowledge_graph_relationship_updated = "knowledge_graph_relationship_updated"
    knowledge_graph_relationship_deleted = "knowledge_graph_relationship_deleted"
    knowledge_graph_evidence_added = "knowledge_graph_evidence_added"
    knowledge_graph_snapshot_created = "knowledge_graph_snapshot_created"
    knowledge_graph_quality_alert = "knowledge_graph_quality_alert"
    knowledge_graph_ingestion_completed = "knowledge_graph_ingestion_completed"
    knowledge_graph_ingestion_failed = "knowledge_graph_ingestion_failed"
    knowledge_graph_duplication_detected = "knowledge_graph_duplication_detected"
    knowledge_graph_resolution_completed = "knowledge_graph_resolution_completed"
    knowledge_graph_health_check = "knowledge_graph_health_check"
    knowledge_graph_stale_detected = "knowledge_graph_stale_detected"
    knowledge_graph_cycle_detected = "knowledge_graph_cycle_detected"
    iam_organization_created = "iam.organization.created"
    iam_organization_suspended = "iam.organization.suspended"
    iam_organization_deleted = "iam.organization.deleted"
    iam_member_added = "iam.member.added"
    iam_member_removed = "iam.member.removed"
    iam_member_suspended = "iam.member.suspended"
    iam_role_changed = "iam.role.changed"
    iam_permission_changed = "iam.permission.changed"
    iam_policy_changed = "iam.policy.changed"
    iam_service_account_created = "iam.service_account.created"
    iam_api_key_created = "iam.api_key.created"
    iam_api_key_revoked = "iam.api_key.revoked"
    iam_access_denied = "iam.access.denied"
    iam_break_glass_started = "iam.break_glass.started"
    iam_break_glass_expired = "iam.break_glass.expired"
    iam_session_created = "iam.session.created"
    iam_session_revoked = "iam.session.revoked"
    iam_quota_exceeded = "iam.quota.exceeded"

    # Customer Support & Service Management events (Volume 54)
    support_ticket_created = "support.ticket.created"
    support_ticket_updated = "support.ticket.updated"
    support_ticket_assigned = "support.ticket.assigned"
    support_ticket_escalated = "support.ticket.escalated"
    support_ticket_linked_to_incident = "support.ticket.linked_to_incident"
    support_ticket_linked_to_issue = "support.ticket.linked_to_issue"
    support_ticket_resolved = "support.ticket.resolved"
    support_ticket_reopened = "support.ticket.reopened"
    support_ai_response_generated = "support.ai.response_generated"
    support_human_handoff_requested = "support.human.handoff_requested"
    support_sla_at_risk = "support.sla.at_risk"
    support_sla_breached = "support.sla.breached"
    support_knowledge_gap_detected = "support.knowledge.gap_detected"
    support_customer_feedback_received = "support.customer.feedback_received"

    # Release Management & Progressive Delivery events (Volume 56)
    release_created = "release.created"
    release_validated = "release.validated"
    release_approval_requested = "release.approval_requested"
    release_approved = "release.approved"
    release_rejected = "release.rejected"
    release_deployment_started = "release.deployment_started"
    release_canary_started = "release.canary_started"
    release_canary_paused = "release.canary_paused"
    release_canary_promoted = "release.canary_promoted"
    release_promoted = "release.promoted"
    release_rolled_back = "release.rolled_back"
    release_failed = "release.failed"
    release_completed = "release.completed"
    release_feature_flag_changed = "release.feature_flag_changed"
    release_verification_completed = "release.verification_completed"

    # Data Governance events (Volume 57)
    governance_data_asset_discovered = "governance.asset.discovered"
    governance_data_classified = "governance.data.classified"
    governance_lineage_updated = "governance.lineage.updated"
    governance_retention_violation_detected = "governance.retention.violation"
    governance_data_request_created = "governance.request.created"
    governance_export_completed = "governance.export.completed"
    governance_policy_violation_detected = "governance.policy.violation"
    governance_control_status_changed = "governance.control.status_changed"
    governance_evidence_collected = "governance.evidence.collected"
    governance_legal_hold_created = "governance.legal_hold.created"
    governance_exception_expired = "governance.exception.expired"
    governance_dlp_violation_detected = "governance.dlp.violation"
    data_redacted = "governance.data.redacted"
    data_export_requested = "governance.data.export_requested"
    data_export_approved = "governance.data.export_approved"

    # AI Governance & MLOps events (Volume 58)
    ai_model_registered = "ai.model.registered"
    ai_model_version_created = "ai.model.version_created"
    ai_evaluation_started = "ai.evaluation.started"
    ai_evaluation_completed = "ai.evaluation.completed"
    ai_model_approved = "ai.model.approved"
    ai_model_blocked = "ai.model.blocked"
    ai_model_deployed = "ai.model.deployed"
    ai_canary_started = "ai.canary.started"
    ai_canary_promoted = "ai.canary.promoted"
    ai_model_rolled_back = "ai.model.rolled_back"
    ai_prompt_version_created = "ai.prompt.version_created"
    ai_guardrail_triggered = "ai.guardrail.triggered"
    ai_policy_denied = "ai.policy.denied"
    ai_policy_approval_required = "ai.policy.approval_required"
    ai_drift_detected = "ai.drift.detected"
    ai_incident_detected = "ai.incident.detected"
    ai_risk_created = "ai.risk.created"
    ai_model_retired = "ai.model.retired"

    # Observability unified platform (Volume 59 Commit 1)
    observability_telemetry_received = "observability.telemetry.received"
    observability_alert_created = "observability.alert.created"
    observability_alert_fired = "observability.alert.fired"
    observability_alert_acknowledged = "observability.alert.acknowledged"
    observability_alert_resolved = "observability.alert.resolved"
    observability_slo_breached = "observability.slo.breached"
    observability_health_changed = "observability.health.changed"
    observability_synthetic_check_failed = "observability.synthetic.check_failed"
    observability_telemetry_retention_completed = "observability.telemetry.retention_completed"

    # Resilience platform (Volume 60)
    resilience_backup_started = "resilience.backup.started"
    resilience_backup_completed = "resilience.backup.completed"
    resilience_backup_failed = "resilience.backup.failed"
    backup_verification_started = "resilience.backup.verification_started"
    backup_verification_completed = "resilience.backup.verification_completed"
    resilience_restore_started = "resilience.restore.started"
    resilience_restore_completed = "resilience.restore.completed"
    resilience_restore_failed = "resilience.restore.failed"
    disaster_declared = "resilience.disaster.declared"
    resilience_recovery_started = "resilience.recovery.started"
    resilience_recovery_completed = "resilience.recovery.completed"
    recovery_failed = "resilience.recovery.failed"
    failover_started = "resilience.failover.started"
    failover_completed = "resilience.failover.completed"

    # Resilience Commit 2 — chaos, drills, hardening (Volume 60)
    chaos_test_started = "resilience.chaos.started"
    chaos_test_completed = "resilience.chaos.completed"
    recovery_drill_started = "resilience.drill.started"
    recovery_drill_completed = "resilience.drill.completed"
    recovery_readiness_changed = "resilience.readiness.changed"
    backup_protection_enabled = "resilience.backup.protection_enabled"
    recovery_reconciliation_created = "resilience.reconciliation.created"
    recovery_verification_failed = "resilience.verification.failed"

    # Performance & Scalability events (Volume 61 Commit 1)
    performance_budget_breached = "performance.budget.breached"
    service_saturated = "performance.service.saturated"
    queue_backlog_detected = "performance.queue.backlog_detected"
    slow_query_detected = "performance.slow_query.detected"
    performance_capacity_warning = "performance.capacity.warning"
    performance_autoscaling_triggered = "performance.autoscaling.triggered"
    performance_load_shedding_started = "performance.load_shedding.started"
    performance_load_shedding_stopped = "performance.load_shedding.stopped"
    # Commit 2 performance events
    capacity_forecast_created = "performance.capacity.forecast_created"
    performance_regression_detected = "performance.regression.detected"
    benchmark_completed = "performance.benchmark.completed"
    stress_test_completed = "performance.stress.completed"
    soak_test_completed = "performance.soak.completed"
    scaling_recommendation_created = "performance.scaling.recommendation_created"
    performance_gate_failed = "performance.gate.failed"
    performance_gate_passed = "performance.gate.passed"

    # Multi-Region platform events (Volume 62 Commit 1) — idempotent lifecycle events
    region_registered = "region.registered"
    region_health_changed = "region.health.changed"
    region_draining_started = "region.draining.started"
    region_draining_completed = "region.draining.completed"
    placement_changed = "region.placement.changed"
    replication_started = "region.replication.started"
    replication_lag_detected = "region.replication.lag_detected"
    replication_recovered = "region.replication.recovered"
    regional_failover_started = "region.failover.started"
    regional_failover_completed = "region.failover.completed"
    regional_failback_started = "region.failback.started"
    regional_failback_completed = "region.failback.completed"

    # Multi-Region Commit 2 — global resilience, consistency & hardening events
    global_failover_triggered = "region.global.failover.triggered"
    global_failover_completed = "region.global.failover.completed"
    failover_blocked = "region.failover.blocked"
    split_brain_detected = "region.split_brain.detected"
    primary_fenced = "region.primary.fenced"
    region_rejoined = "region.rejoined"
    tenant_migration_started = "region.tenant.migration.started"
    tenant_migration_completed = "region.tenant.migration.completed"
    replication_conflict_detected = "region.replication.conflict.detected"
    configuration_drift_detected = "region.config.drift.detected"
    regional_recovery_verified = "region.recovery.verified"

    # SecOps — Volume 63 Commit 1
    security_event_received = "secops.event.received"
    security_alert_created = "secops.alert.created"
    security_finding_created = "secops.finding.created"
    security_case_created = "secops.case.created"
    security_case_updated = "secops.case.updated"
    threat_indicator_matched = "secops.indicator.matched"
    security_risk_changed = "secops.risk.changed"
    security_alert_resolved = "secops.alert.resolved"

    # SecOps — Volume 63 Commit 2
    security_response_requested = "secops.response.requested"
    security_response_approved = "secops.response.approved"
    security_response_started = "secops.response.started"
    security_response_completed = "secops.response.completed"
    security_response_failed = "secops.response.failed"
    threat_hunt_started = "secops.hunt.started"
    threat_hunt_completed = "secops.hunt.completed"
    containment_verified = "secops.containment.verified"
    security_control_test_completed = "secops.control_test.completed"
    detection_coverage_changed = "secops.coverage.changed"

    # Zero Trust — Volume 64 Commit 1
    IdentityCreated = "zero_trust.identity.created"
    IdentitySuspended = "zero_trust.identity.suspended"
    SessionCreated = "zero_trust.session.created"
    SessionRevoked = "zero_trust.session.revoked"
    CredentialCreated = "zero_trust.credential.created"
    CredentialExpired = "zero_trust.credential.expired"
    CredentialRevoked = "zero_trust.credential.revoked"
    AccessRequested = "zero_trust.access.requested"
    AccessApproved = "zero_trust.access.approved"
    AccessDenied = "zero_trust.access.denied"
    PrivilegedAccessGranted = "zero_trust.privileged.granted"
    PrivilegedAccessExpired = "zero_trust.privileged.expired"
    AuthorizationPolicyChanged = "zero_trust.policy.changed"

    # Zero Trust — Volume 64 Commit 2
    IdentityRiskChanged = "zero_trust.risk.changed"
    AccessAnomalyDetected = "zero_trust.anomaly.detected"
    StepUpRequired = "zero_trust.stepup.required"
    SessionRiskChanged = "zero_trust.session.risk_changed"
    CredentialRotationStarted = "zero_trust.credential.rotation_started"
    CredentialRotationCompleted = "zero_trust.credential.rotation_completed"
    PrivilegeRiskDetected = "zero_trust.privilege.risk_detected"
    AccessReviewStarted = "zero_trust.review.started"
    AccessReviewCompleted = "zero_trust.review.completed"
    ZeroTrustPostureChanged = "zero_trust.posture.changed"

    # Observability AIOps extensions (Volume 59 Commit 2) — additive, no placeholders
    AnomalyDetected = "observability.anomaly.detected"
    AlertCorrelated = "observability.alert.correlated"
    RootCauseCandidateCreated = "observability.root_cause.candidate_created"
    AIOpsRecommendationCreated = "observability.aiops.recommendation_created"
    RemediationRequested = "observability.remediation.requested"
    RemediationApproved = "observability.remediation.approved"
    RemediationStarted = "observability.remediation.started"
    RemediationCompleted = "observability.remediation.completed"
    RemediationFailed = "observability.remediation.failed"
    AgentCircuitBroken = "observability.agent.circuit_broken"
    CapacityForecastGenerated = "observability.capacity.forecast_generated"
    # snake_case aliases (backward compat, same values)
    anomaly_detected = "observability.anomaly.detected"
    alert_correlated = "observability.alert.correlated"
    root_cause_candidate_created = "observability.root_cause.candidate_created"
    aiops_recommendation_created = "observability.aiops.recommendation_created"
    remediation_requested = "observability.remediation.requested"
    remediation_approved = "observability.remediation.approved"
    remediation_started = "observability.remediation.started"
    remediation_completed = "observability.remediation.completed"
    remediation_failed = "observability.remediation.failed"
    agent_circuit_broken = "observability.agent.circuit_broken"
    capacity_forecast_generated = "observability.capacity.forecast_generated"


class Event:
    def __init__(
        self,
        event_type: EventType,
        data: dict,
        source: str = "system",
        organization_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())
        self.event_type = event_type
        self.data = data
        self.source = source
        self.organization_id = organization_id
        self.user_id = user_id
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.version = "1.0"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.event_type.value,
            "data": self.data,
            "source": self.source,
            "organization_id": self.organization_id,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        e = cls.__new__(cls)
        e.id = d.get("id", str(uuid.uuid4()))
        e.event_type = EventType(d["type"])
        e.data = d.get("data", {})
        e.source = d.get("source", "system")
        e.organization_id = d.get("organization_id")
        e.user_id = d.get("user_id")
        e.timestamp = d.get("timestamp", datetime.now(timezone.utc).isoformat())
        e.version = d.get("version", "1.0")
        return e


EventHandler = Callable[[Event], Any]


class EventBus:
    """Async event bus with Redis persistence, in-memory subscribers, and replay."""

    def __init__(self):
        self._subscribers: dict[EventType, list[EventHandler]] = {}
        self._global_subscribers: list[EventHandler] = []
        self._running = False
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

    def subscribe(self, event_type: EventType, handler: EventHandler):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: EventHandler):
        self._global_subscribers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler):
        if event_type in self._subscribers:
            self._subscribers[event_type] = [h for h in self._subscribers[event_type] if h is not handler]

    async def publish(self, event: Event) -> None:
        await self._persist(event)
        await self._queue.put(event)

    async def publish_nowait(self, event: Event) -> None:
        await self._persist(event)
        for handler in self._subscribers.get(event.event_type, []):
            await self._safe_call(handler, event)
        for handler in self._global_subscribers:
            await self._safe_call(handler, event)

    async def _persist(self, event: Event) -> None:
        try:
            redis = await get_redis()
            key = f"events:{event.event_type.value}:{event.id}"
            await redis.setex(key, 86400 * 7, json.dumps(event.to_dict()))
            await redis.lpush(f"events:recent:{event.event_type.value}", json.dumps(event.to_dict()))
            await redis.ltrim(f"events:recent:{event.event_type.value}", 0, 999)
        except Exception:
            pass

    async def _safe_call(self, handler: EventHandler, event: Event) -> None:
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass

    async def start(self):
        self._running = True
        self._worker_task = asyncio.create_task(self._process_queue())

    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _process_queue(self):
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                for handler in self._subscribers.get(event.event_type, []):
                    await self._safe_call(handler, event)
                for handler in self._global_subscribers:
                    await self._safe_call(handler, event)
            except asyncio.TimeoutError:
                continue
            except Exception:
                continue

    async def replay(self, event_type: Optional[EventType] = None, limit: int = 100) -> list[Event]:
        events = []
        try:
            redis = await get_redis()
            if event_type:
                raw = await redis.lrange(f"events:recent:{event_type.value}", 0, limit - 1)
            else:
                raw = []
                for et in EventType:
                    batch = await redis.lrange(f"events:recent:{et.value}", 0, limit // len(EventType))
                    raw.extend(batch)
            for item in raw:
                try:
                    events.append(Event.from_dict(json.loads(item)))
                except Exception:
                    continue
        except Exception:
            pass
        return events

    async def get_recent(self, event_type: Optional[str] = None, limit: int = 50) -> list[dict]:
        events = await self.replay(
            EventType(event_type) if event_type else None,
            limit,
        )
        return [e.to_dict() for e in events]


event_bus = EventBus()
