"""SRE operational events (Volume 35).

Emission wrapper over the existing core event bus. All SRE events are
idempotent: they carry a stable event key (e.g. the service or SLO id)
inside the payload and consumers must deduplicate on that key. Emission
never raises - operational events must not break the request path.
"""

import logging
from typing import Optional

from app.core.events import Event, EventType, event_bus

logger = logging.getLogger(__name__)

# Event payload keys used for idempotency + correlation.
EVENT_KEY = "event_key"
CORRELATION = "correlation_id"


def emit_sre_event(
    event_type: EventType,
    *,
    event_key: str,
    data: Optional[dict] = None,
    source: str = "sre",
    organization_id: Optional[str] = None,
    user_id: Optional[str] = None,
    correlation_id: str = "",
) -> None:
    """Publish an SRE event with a stable event_key for idempotent consumption."""
    if event_type not in EventType:
        logger.warning("attempted to emit unknown event type %s", event_type)
        return
    payload = dict(data or {})
    payload[EVENT_KEY] = event_key
    payload[CORRELATION] = correlation_id
    event = Event(
        event_type=event_type,
        data=payload,
        source=source,
        organization_id=organization_id,
        user_id=user_id,
    )
    try:
        event_bus.publish_nowait(event)
    except Exception as exc:  # pragma: no cover - events must not break flows
        logger.warning("failed to publish SRE event %s: %s", event_type.value, exc)


def service_degraded(service_id: str, region: str = "", **data) -> None:
    emit_sre_event(EventType.service_degraded, event_key=f"service:{service_id}:{region}", data={"service_id": service_id, "region": region, **data}, correlation_id=f"svc-{service_id}")


def service_recovered(service_id: str, region: str = "", **data) -> None:
    emit_sre_event(EventType.service_recovered, event_key=f"service:{service_id}:{region}", data={"service_id": service_id, "region": region, **data}, correlation_id=f"svc-{service_id}")


def slo_violation(slo_id: str, service_id: str, **data) -> None:
    emit_sre_event(EventType.slo_violation, event_key=f"slo:{slo_id}", data={"slo_id": slo_id, "service_id": service_id, **data}, correlation_id=f"slo-{slo_id}")


def error_budget_burning(slo_id: str, service_id: str, tier: str, **data) -> None:
    emit_sre_event(EventType.error_budget_burning, event_key=f"budget:{slo_id}:{tier}", data={"slo_id": slo_id, "service_id": service_id, "tier": tier, **data}, correlation_id=f"budget-{slo_id}")


def incident_created(incident_id: str, **data) -> None:
    emit_sre_event(EventType.incident_created, event_key=f"incident:{incident_id}", data={"incident_id": incident_id, **data}, correlation_id=incident_id)


def incident_updated(incident_id: str, status: str, **data) -> None:
    emit_sre_event(EventType.incident_updated, event_key=f"incident:{incident_id}:{status}", data={"incident_id": incident_id, "status": status, **data}, correlation_id=incident_id)


def incident_resolved(incident_id: str, **data) -> None:
    emit_sre_event(EventType.incident_resolved, event_key=f"incident:{incident_id}", data={"incident_id": incident_id, **data}, correlation_id=incident_id)


def deployment_failed(deployment_id: str, service_id: str, **data) -> None:
    emit_sre_event(EventType.deployment_failed, event_key=f"deploy:{deployment_id}", data={"deployment_id": deployment_id, "service_id": service_id, **data}, correlation_id=f"deploy-{deployment_id}")


def rollback_triggered(deployment_id: str, service_id: str, reason: str, **data) -> None:
    emit_sre_event(EventType.rollback_triggered, event_key=f"rollback:{deployment_id}", data={"deployment_id": deployment_id, "service_id": service_id, "reason": reason, **data}, correlation_id=f"deploy-{deployment_id}")


def dependency_outage(dependency: str, kind: str = "", **data) -> None:
    emit_sre_event(EventType.dependency_outage, event_key=f"dep:{dependency}", data={"dependency": dependency, "kind": kind, **data}, correlation_id=f"dep-{dependency}")


def region_degraded(region: str, **data) -> None:
    emit_sre_event(EventType.region_degraded, event_key=f"region:{region}", data={"region": region, **data}, correlation_id=f"region-{region}")


def backup_failed(backup_id: str, target: str, **data) -> None:
    emit_sre_event(EventType.backup_failed, event_key=f"backup:{backup_id}", data={"backup_id": backup_id, "target": target, **data}, correlation_id=f"backup-{backup_id}")


def restore_failed(test_id: str, target: str, **data) -> None:
    emit_sre_event(EventType.restore_failed, event_key=f"restore:{test_id}", data={"test_id": test_id, "target": target, **data}, correlation_id=f"restore-{test_id}")


def capacity_warning(service_id: str, metric: str, **data) -> None:
    emit_sre_event(EventType.capacity_warning, event_key=f"capacity:{service_id}:{metric}", data={"service_id": service_id, "metric": metric, **data}, correlation_id=f"cap-{service_id}-{metric}")


def certificate_expiring(name: str, hostname: str, **data) -> None:
    emit_sre_event(EventType.certificate_expiring, event_key=f"cert:{hostname}", data={"name": name, "hostname": hostname, **data}, correlation_id=f"cert-{hostname}")