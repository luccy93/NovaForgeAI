"""Maintenance windows and status components (Volume 35)."""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import (
    MAINTENANCE_CANCELLED,
    MAINTENANCE_COMPLETED,
    MAINTENANCE_IN_PROGRESS,
    MAINTENANCE_SCHEDULED,
    STATUS_DEGRADED,
    STATUS_MAJOR_OUTAGE,
    STATUS_MAINTENANCE,
    STATUS_OPERATIONAL,
    STATUS_PARTIAL_OUTAGE,
    STATUS_UNKNOWN,
)
from app.sre.models import SREIncident, SREMaintenanceWindow, SREStatusComponent
from app.sre.store import get_one, list_all, new_id, new_key

logger = logging.getLogger(__name__)

MAINTENANCE_SCOPES = ["org", "region", "service", "database"]
MAINTENANCE_STATUSES = [MAINTENANCE_SCHEDULED, MAINTENANCE_IN_PROGRESS, MAINTENANCE_COMPLETED, MAINTENANCE_CANCELLED]

STATUS_STATES = [STATUS_OPERATIONAL, STATUS_DEGRADED, STATUS_PARTIAL_OUTAGE, STATUS_MAJOR_OUTAGE, STATUS_MAINTENANCE, STATUS_UNKNOWN]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MaintenanceWindowManager:
    """Maintenance window lifecycle."""

    async def schedule(
        self,
        db: AsyncSession,
        *,
        scope: str,
        target: str,
        starts_at: datetime,
        ends_at: datetime,
        description: str = "",
        organization_id: str = "",
        created_by: str = "",
    ) -> SREMaintenanceWindow:
        if scope not in MAINTENANCE_SCOPES:
            raise ValueError(f"invalid scope: {scope}")
        if ends_at <= starts_at:
            raise ValueError("ends_at must be after starts_at")
        window = SREMaintenanceWindow(
            id=new_id(),
            maintenance_id=new_key("maint"),
            organization_id=organization_id,
            scope=scope,
            target=target,
            description=description,
            status=MAINTENANCE_SCHEDULED,
            starts_at=starts_at,
            ends_at=ends_at,
            created_by=created_by,
        )
        db.add(window)
        await db.flush()
        return window

    async def set_status(self, db: AsyncSession, maintenance_id: str, status: str) -> Optional[SREMaintenanceWindow]:
        if status not in MAINTENANCE_STATUSES:
            raise ValueError(f"invalid maintenance status: {status}")
        window = await get_one(db, SREMaintenanceWindow, maintenance_id=maintenance_id)
        if window is None:
            return None
        window.status = status
        await db.flush()
        return window

    async def current(self, db: AsyncSession, *, target: str = "", scope: str = "") -> list[dict]:
        now = _utcnow()
        result = await db.execute(
            select(SREMaintenanceWindow).where(
                SREMaintenanceWindow.status.in_([MAINTENANCE_SCHEDULED, MAINTENANCE_IN_PROGRESS]),
                SREMaintenanceWindow.ends_at > now,
            )
        )
        windows = result.scalars().all()
        if target:
            windows = [w for w in windows if w.target == target]
        if scope:
            windows = [w for w in windows if w.scope == scope]
        return [self._to_dict(w, now) for w in windows]

    def _to_dict(self, window: SREMaintenanceWindow, now: datetime) -> dict:
        data = {
            "maintenance_id": window.maintenance_id,
            "scope": window.scope,
            "target": window.target,
            "description": window.description,
            "status": window.status,
            "starts_at": window.starts_at.isoformat(),
            "ends_at": window.ends_at.isoformat(),
            "created_by": window.created_by,
        }
        data["active"] = window.starts_at <= now <= window.ends_at and window.status != MAINTENANCE_CANCELLED
        return data

    async def list(self, db: AsyncSession, *, status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        items, total = await list_all(
            db, SREMaintenanceWindow, limit=limit, offset=offset, order_by="starts_at", status=status
        )
        now = _utcnow()
        return [self._to_dict(w, now) for w in items], total


class StatusManager:
    """Status page components + aggregate platform status."""

    async def register_component(
        self,
        db: AsyncSession,
        *,
        name: str,
        service_id: str = "",
        description: str = "",
        region: str = "",
        public: bool = False,
        component_id: Optional[str] = None,
    ) -> SREStatusComponent:
        component_id = component_id or new_key("comp")
        existing = await get_one(db, SREStatusComponent, component_id=component_id)
        if existing:
            return existing
        component = SREStatusComponent(
            id=new_id(),
            component_id=component_id,
            service_id=service_id,
            name=name,
            description=description,
            status=STATUS_OPERATIONAL,
            region=region,
            public=public,
        )
        db.add(component)
        await db.flush()
        return component

    async def update_status(
        self,
        db: AsyncSession,
        component_id: str,
        status: str,
    ) -> Optional[SREStatusComponent]:
        if status not in STATUS_STATES:
            raise ValueError(f"invalid status: {status}")
        component = await get_one(db, SREStatusComponent, component_id=component_id)
        if component is None:
            return None
        if component.status != status:
            history = list(component.history or [])
            history.append({"status": component.status, "changed_at": _utcnow().isoformat()})
            component.history = history[-200:]
            component.status = status
            await db.flush()
        return component

    async def components(self, db: AsyncSession, *, public_only: bool = False) -> "list[dict]":
        result = await db.execute(select(SREStatusComponent))
        components = result.scalars().all()
        if public_only:
            components = [c for c in components if c.public]
        return [c.to_dict() for c in components]

    async def aggregate(self, db: AsyncSession) -> dict:
        """Derive platform status from component states + open incidents."""
        components = await self.components(db)
        statuses = [c["status"] for c in components]
        open_incidents = (
            await db.execute(
                select(SREIncident).where(
                    SREIncident.status.notin_(["resolved", "closed"])
                )
            )
        ).scalars().all()

        if STATUS_MAJOR_OUTAGE in statuses or any(i.severity == "SEV0" for i in open_incidents):
            overall = STATUS_MAJOR_OUTAGE
        elif STATUS_PARTIAL_OUTAGE in statuses or any(i.severity == "SEV1" for i in open_incidents):
            overall = STATUS_PARTIAL_OUTAGE
        elif STATUS_DEGRADED in statuses:
            overall = STATUS_DEGRADED
        elif any(c["status"] == STATUS_MAINTENANCE for c in components):
            overall = STATUS_MAINTENANCE
        elif statuses:
            overall = STATUS_OPERATIONAL
        else:
            overall = STATUS_UNKNOWN
        return {
            "status": overall,
            "components": components,
            "active_incidents": [i.incident_id for i in open_incidents],
        }


maintenance_window_manager = MaintenanceWindowManager()
status_manager = StatusManager()
