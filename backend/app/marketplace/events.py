"""Marketplace event publishing (EventBus + webhook delivery)."""

from typing import Optional

from app.core.events import Event, EventBus, EventType

event_bus = EventBus()

MARKETPLACE_EVENTS = {
    "PackagePublished": EventType.marketplace_package_published,
    "PackageUpdated": EventType.marketplace_package_updated,
    "PackageInstalled": EventType.marketplace_package_installed,
    "PackageUninstalled": EventType.marketplace_package_uninstalled,
    "PackageSuspended": EventType.marketplace_package_suspended,
    "PackageReported": EventType.marketplace_package_reported,
    "PackageSecurityIssue": EventType.marketplace_package_security_issue,
    "PackageDeprecated": EventType.marketplace_package_deprecated,
    "PackageRetired": EventType.marketplace_package_retired,
}


async def publish(event_name: str, data: dict, organization_id: Optional[str] = None, user_id: Optional[str] = None) -> None:
    """Publish a marketplace lifecycle event to the bus.

    Best-effort: a missing Redis/worker does not break the request, but every
    meaningful lifecycle action is also recorded in the ``marketplace_package_events``
    audit table by the calling service.
    """
    etype = MARKETPLACE_EVENTS.get(event_name)
    if not etype:
        return
    try:
        await event_bus.publish(Event(etype, data, source="marketplace", organization_id=organization_id, user_id=user_id))
    except Exception:
        # Event streaming is non-critical; audit log remains the source of truth.
        pass
