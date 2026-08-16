"""Postmortems and corrective action tracking (Volume 35).

Blame-free postmortems for SEV0/SEV1 incidents with corrective action
tracking (owner, priority, due date, status, verification).
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.models import SRECorrectiveAction, SREIncident, SREPostmortem
from app.sre.store import get_one, list_all, new_id, new_key

logger = logging.getLogger(__name__)

VALID_ACTION_STATUSES = ["open", "in_progress", "done", "verified", "wont_do"]
VALID_PRIORITIES = ["high", "medium", "low"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PostmortemManager:
    """Postmortem lifecycle + corrective actions."""

    async def create(
        self,
        db: AsyncSession,
        *,
        incident_id: str,
        summary: str = "",
        impact: str = "",
        root_cause: str = "",
        timeline: Optional[list] = None,
        contributing_factors: Optional[list[str]] = None,
        detection: str = "",
        response: str = "",
        what_went_well: Optional[list[str]] = None,
        what_went_wrong: Optional[list[str]] = None,
        created_by: str = "",
    ) -> SREPostmortem:
        incident = await get_one(db, SREIncident, incident_id=incident_id)
        if incident is None:
            raise ValueError(f"incident not found: {incident_id}")
        postmortem = SREPostmortem(
            id=new_id(),
            postmortem_id=new_key("pm"),
            incident_id=incident_id,
            summary=summary,
            impact=impact,
            timeline=timeline or [],
            root_cause=root_cause,
            contributing_factors=contributing_factors or [],
            detection=detection,
            response=response,
            what_went_well=what_went_well or [],
            what_went_wrong=what_went_wrong or [],
            status="draft",
            created_by=created_by,
        )
        db.add(postmortem)
        await db.flush()
        incident.postmortem_id = postmortem.postmortem_id
        await db.flush()
        return postmortem

    async def draft_from_incident(self, db: AsyncSession, incident_id: str) -> SREPostmortem:
        """Auto-draft a postmortem skeleton from the incident record."""
        incident = await get_one(db, SREIncident, incident_id=incident_id)
        if incident is None:
            raise ValueError(f"incident not found: {incident_id}")
        if incident.postmortem_id:
            existing = await get_one(db, SREPostmortem, postmortem_id=incident.postmortem_id)
            if existing:
                return existing
        from app.sre.incident import incident_manager

        timeline = await incident_manager.timeline(db, incident_id)
        return await self.create(
            db,
            incident_id=incident_id,
            summary=f"Postmortem for incident {incident_id}",
            impact=incident.impact.get("description", "") if incident.impact else "",
            root_cause=incident.root_cause,
            timeline=timeline,
            contributing_factors=[],
            detection=incident.detection,
            response="",
            created_by="system",
        )

    async def update(
        self,
        db: AsyncSession,
        postmortem_id: str,
        **values: dict,
    ) -> Optional[SREPostmortem]:
        postmortem = await get_one(db, SREPostmortem, postmortem_id=postmortem_id)
        if postmortem is None:
            return None
        for key, value in values.items():
            if hasattr(postmortem, key) and key not in ("id", "postmortem_id", "incident_id"):
                setattr(postmortem, key, value)
        await db.flush()
        return postmortem

    async def publish(self, db: AsyncSession, postmortem_id: str) -> Optional[SREPostmortem]:
        postmortem = await get_one(db, SREPostmortem, postmortem_id=postmortem_id)
        if postmortem is None:
            return None
        if postmortem.status == "draft":
            postmortem.status = "published"
            await db.flush()
        return postmortem

    async def get(self, db: AsyncSession, postmortem_id: str) -> Optional[dict]:
        postmortem = await get_one(db, SREPostmortem, postmortem_id=postmortem_id)
        return postmortem.to_dict() if postmortem else None

    async def list(self, db: AsyncSession, *, status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        items, total = await list_all(
            db, SREPostmortem, limit=limit, offset=offset, order_by="created_at", status=status
        )
        return [p.to_dict() for p in items], total


class CorrectiveActionManager:
    """Corrective action tracking with verification."""

    async def create(
        self,
        db: AsyncSession,
        *,
        description: str,
        incident_id: str = "",
        postmortem_id: str = "",
        owner: str = "",
        priority: str = "medium",
        due_date: Optional[datetime] = None,
    ) -> SRECorrectiveAction:
        if priority not in VALID_PRIORITIES:
            raise ValueError(f"invalid priority: {priority}")
        action = SRECorrectiveAction(
            id=new_id(),
            action_id=new_key("ca"),
            incident_id=incident_id,
            postmortem_id=postmortem_id,
            description=description,
            owner=owner,
            priority=priority,
            status="open",
            due_date=due_date,
        )
        db.add(action)
        await db.flush()
        return action

    async def update_status(
        self,
        db: AsyncSession,
        action_id: str,
        status: str,
        *,
        verification: str = "",
        owner: str = "",
    ) -> Optional[SRECorrectiveAction]:
        if status not in VALID_ACTION_STATUSES:
            raise ValueError(f"invalid action status: {status}")
        action = await get_one(db, SRECorrectiveAction, action_id=action_id)
        if action is None:
            return None
        action.status = status
        if verification:
            action.verification = verification
        if owner:
            action.owner = owner
        await db.flush()
        return action

    async def list(
        self,
        db: AsyncSession,
        *,
        incident_id: str = "",
        status: str = "",
        priority: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        items, total = await list_all(
            db,
            SRECorrectiveAction,
            limit=limit,
            offset=offset,
            order_by="created_at",
            incident_id=incident_id,
            status=status,
            priority=priority,
        )
        return [a.to_dict() for a in items], total

    async def open_actions(self, db: AsyncSession) -> List[dict]:
        items, _ = await list_all(db, SRECorrectiveAction, limit=200, status="open")
        return [a.to_dict() for a in items]

    async def overdue(self, db: AsyncSession) -> List[dict]:
        result = await db.execute(
            select(SRECorrectiveAction).where(
                SRECorrectiveAction.status.in_(["open", "in_progress"]),
                SRECorrectiveAction.due_date.is_not(None),
                SRECorrectiveAction.due_date < _utcnow(),
            )
        )
        return [a.to_dict() for a in result.scalars().all()]


postmortem_manager = PostmortemManager()
corrective_action_manager = CorrectiveActionManager()
