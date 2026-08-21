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
