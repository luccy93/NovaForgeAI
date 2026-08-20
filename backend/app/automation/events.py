"""Event types for the Autonomous Software-Engineering layer (Volume 45)."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AutomationEvent:
    event_type: str
    task_id: str
    data: dict[str, Any] = field(default_factory=dict)
    tenant: str = ""
    actor: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = "1.0"


# Event type constants matching the spec
AUTOMATION_STARTED = "automation_started"
PLAN_CREATED = "plan_created"
APPROVAL_REQUIRED = "approval_required"
PATCH_GENERATED = "patch_generated"
TESTS_STARTED = "tests_started"
TESTS_PASSED = "tests_passed"
TESTS_FAILED = "tests_failed"
REVIEW_COMPLETED = "review_completed"
SECURITY_GATE_FAILED = "security_gate_failed"
DEPLOYMENT_STARTED = "deployment_started"
DEPLOYMENT_COMPLETED = "deployment_completed"
ROLLBACK_TRIGGERED = "rollback_triggered"
AUTOMATION_COMPLETED = "automation_completed"
AUTOMATION_FAILED = "automation_failed"


async def emit_automation_event(event_type: str, task_id: str, data: dict | None = None,
                                tenant: str = "", actor: str = "") -> AutomationEvent:
    event = AutomationEvent(
        event_type=event_type,
        task_id=task_id,
        data=data or {},
        tenant=tenant,
        actor=actor,
    )
    try:
        from app.core.events import event_bus, Event, EventType
        event_type_map = {
            AUTOMATION_STARTED: EventType.deployment_started,
            AUTOMATION_COMPLETED: EventType.deployment_completed,
            AUTOMATION_FAILED: EventType.deployment_failed,
        }
        core_type = event_type_map.get(event_type)
        if core_type:
            bus_event = Event(
                event_type=core_type,
                data={"task_id": task_id, **(data or {})},
                source="automation",
                organization_id=tenant,
                user_id=actor,
            )
            await event_bus.publish(core_type, bus_event)
    except Exception:
        logger.debug("event bus unavailable, event %s for task %s dropped", event_type, task_id)
    return event
