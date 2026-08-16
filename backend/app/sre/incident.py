"""Incident management (Volume 35).

Structured incident lifecycle (detected -> investigating -> identified ->
mitigating -> monitoring -> resolved -> closed), command roles, automatic
timelines, correlation with changes/deployments/alerts, and advisory
AI-assisted diagnosis.

AI diagnosis is advisory only: it never fabricates root causes and never
executes remediation.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import (
    INCIDENT_CLOSED,
    INCIDENT_COMMAND_ROLES,
    INCIDENT_DETECTED,
    INCIDENT_IDENTIFIED,
    INCIDENT_INVESTIGATING,
    INCIDENT_MITIGATING,
    INCIDENT_MONITORING,
    INCIDENT_RESOLVED,
    INCIDENT_STATES,
    SEVERITIES,
    SEVERITY_DEFAULT_TARGET_MINUTES,
    SEV1,
    SEV2,
)
from app.sre.models import (
    SREAlert,
    SREDeployment,
    SREIncident,
    SREIncidentEvent,
    SREIncidentResponder,
    SREPostmortem,
)
from app.sre.store import get_one, list_all, new_id, new_key

logger = logging.getLogger(__name__)

VALID_TRANSITIONS: dict[str, list[str]] = {
    INCIDENT_DETECTED: [INCIDENT_INVESTIGATING, INCIDENT_MITIGATING, INCIDENT_RESOLVED],
    INCIDENT_INVESTIGATING: [INCIDENT_IDENTIFIED, INCIDENT_MITIGATING, INCIDENT_RESOLVED],
    INCIDENT_IDENTIFIED: [INCIDENT_MITIGATING, INCIDENT_MONITORING, INCIDENT_RESOLVED],
    INCIDENT_MITIGATING: [INCIDENT_MONITORING, INCIDENT_RESOLVED],
    INCIDENT_MONITORING: [INCIDENT_RESOLVED, INCIDENT_MITIGATING],
    INCIDENT_RESOLVED: [INCIDENT_CLOSED, INCIDENT_MONITORING],
    INCIDENT_CLOSED: [],
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IncidentManager:
    """DB-backed incident lifecycle, command, timeline, correlation."""

    # ------------------------------------------------------------ creation
    async def create(
        self,
        db: AsyncSession,
        *,
        title: str,
        severity: str = SEV2,
        description: str = "",
        organization_id: str = "",
        service_id: str = "",
        region: str = "",
        commander: str = "",
        detection: str = "alert",
        impact: Optional[dict] = None,
    ) -> SREIncident:
        if severity not in SEVERITIES:
            raise ValueError(f"invalid severity {severity!r}; must be one of {SEVERITIES}")
        now = _utcnow()
        incident = SREIncident(
            id=new_id(),
            incident_id=new_key("inc"),
            organization_id=organization_id,
            title=title,
            description=description,
            severity=severity,
            status=INCIDENT_DETECTED,
            service_id=service_id,
            region=region,
            commander=commander,
            detection=detection,
            impact=impact or {},
            detected_at=now,
        )
        db.add(incident)
        await db.flush()
        await self.add_timeline_event(db, incident.incident_id, "detected", "system", f"Incident created ({detection})")
        if commander:
            await self.assign_role(db, incident.incident_id, "incident_commander", commander)
        return incident

    # ----------------------------------------------------------- lifecycle
    async def transition(self, db: AsyncSession, incident_id: str, new_status: str, actor: str = "system") -> Optional[SREIncident]:
        incident = await get_one(db, SREIncident, incident_id=incident_id)
        if incident is None:
            return None
        if new_status not in INCIDENT_STATES:
            raise ValueError(f"invalid incident state: {new_status}")
        allowed = VALID_TRANSITIONS.get(incident.status, [])
        if new_status not in allowed:
            raise ValueError(f"invalid transition {incident.status} -> {new_status} (allowed: {allowed})")
        now = _utcnow()
        incident.status = new_status
        if new_status == INCIDENT_RESOLVED and incident.resolved_at is None:
            incident.resolved_at = now
        if new_status == INCIDENT_CLOSED:
            incident.closed_at = now
        await db.flush()
        await self.add_timeline_event(db, incident_id, "status", actor, f"Status -> {new_status}")
        return incident

    async def acknowledge(self, db: AsyncSession, incident_id: str, actor: str = "system") -> Optional[SREIncident]:
        incident = await get_one(db, SREIncident, incident_id=incident_id)
        if incident is None:
            return None
        if incident.acknowledged_at is None:
            incident.acknowledged_at = _utcnow()
            await db.flush()
            await self.add_timeline_event(db, incident_id, "ack", actor, "Incident acknowledged")
        return incident

    async def update_impact(
        self,
        db: AsyncSession,
        incident_id: str,
        *,
        impact: Optional[dict] = None,
        root_cause: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[SREIncident]:
        incident = await get_one(db, SREIncident, incident_id=incident_id)
        if incident is None:
            return None
        if impact is not None:
            incident.impact = impact
        if root_cause is not None:
            incident.root_cause = root_cause
        if description is not None:
            incident.description = description
        await db.flush()
        return incident

    async def mitigate(self, db: AsyncSession, incident_id: str, actor: str = "system") -> Optional[SREIncident]:
        incident = await get_one(db, SREIncident, incident_id=incident_id)
        if incident is None:
            return None
        if incident.mitigated_at is None:
            incident.mitigated_at = _utcnow()
            await db.flush()
            await self.add_timeline_event(db, incident_id, "mitigation", actor, "Incident mitigated")
        return incident

    async def correlate(
        self,
        db: AsyncSession,
        incident_id: str,
        *,
        deployment_ids: Optional[list[str]] = None,
        alert_ids: Optional[list[str]] = None,
        changes: Optional[list[str]] = None,
    ) -> Optional[SREIncident]:
        """Attach related deployments, alerts, and change references."""
        incident = await get_one(db, SREIncident, incident_id=incident_id)
        if incident is None:
            return None
        if deployment_ids:
            incident.related_deployments = list(dict.fromkeys([*incident.related_deployments, *deployment_ids]))
        if alert_ids:
            incident.related_alerts = list(dict.fromkeys([*incident.related_alerts, *alert_ids]))
        if changes:
            incident.related_changes = list(dict.fromkeys([*incident.related_changes, *changes]))
        await db.flush()
        return incident

    # ------------------------------------------------------------ command
    async def assign_role(self, db: AsyncSession, incident_id: str, role: str, user_id: str) -> Optional[SREIncidentResponder]:
        if role not in INCIDENT_COMMAND_ROLES:
            raise ValueError(f"invalid command role: {role}")
        existing = await get_one(db, SREIncidentResponder, incident_id=incident_id, role=role)
        if existing is not None:
            existing.user_id = user_id
            await db.flush()
            return existing
        responder = SREIncidentResponder(id=new_id(), incident_id=incident_id, role=role, user_id=user_id)
        db.add(responder)
        await db.flush()
        await self.add_timeline_event(db, incident_id, "command", "system", f"{role} assigned to {user_id}")
        return responder

    async def responders(self, db: AsyncSession, incident_id: str) -> list[dict]:
        result = await db.execute(
            select(SREIncidentResponder).where(SREIncidentResponder.incident_id == incident_id)
        )
        return [
            {"role": r.role, "user_id": r.user_id, "assigned_at": r.assigned_at.isoformat()}
            for r in result.scalars().all()
        ]

    # ------------------------------------------------------------ timeline
    async def add_timeline_event(
        self,
        db: AsyncSession,
        incident_id: str,
        event_type: str,
        actor: str = "system",
        message: str = "",
        metadata: Optional[dict] = None,
    ) -> SREIncidentEvent:
        entry = SREIncidentEvent(
            id=new_id(),
            incident_id=incident_id,
            event_type=event_type,
            actor=actor,
            message=message,
            metadata_json=metadata or {},
        )
        db.add(entry)
        await db.flush()
        return entry

    async def timeline(self, db: AsyncSession, incident_id: str) -> list[dict]:
        result = await db.execute(
            select(SREIncidentEvent)
            .where(SREIncidentEvent.incident_id == incident_id)
            .order_by(SREIncidentEvent.occurred_at.asc())
        )
        return [
            {
                "event_type": e.event_type,
                "actor": e.actor,
                "message": e.message,
                "metadata": e.metadata_json or {},
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in result.scalars().all()
        ]

    # ------------------------------------------------------------- queries
    async def get(self, db: AsyncSession, incident_id: str) -> Optional[dict]:
        incident = await get_one(db, SREIncident, incident_id=incident_id)
        if incident is None:
            return None
        data = incident.to_dict()
        data["timeline"] = await self.timeline(db, incident_id)
        data["responders"] = await self.responders(db, incident_id)
        return data

    async def list(
        self,
        db: AsyncSession,
        *,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        service_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        items, total = await list_all(
            db,
            SREIncident,
            limit=limit,
            offset=offset,
            order_by="detected_at",
            status=status,
            severity=severity,
            service_id=service_id,
            organization_id=organization_id or "",
        )
        return [i.to_dict() for i in items], total

    async def active(self, db: AsyncSession) -> List[dict]:
        result = await db.execute(
            select(SREIncident)
            .where(SREIncident.status.notin_([INCIDENT_RESOLVED, INCIDENT_CLOSED]))
            .order_by(SREIncident.detected_at.desc())
        )
        incidents = result.scalars().all()
        return [i.to_dict() for i in incidents]

    # --------------------------------------------------- auto-detection
    async def detect_from_alert(
        self,
        db: AsyncSession,
        alert: SREAlert,
        *,
        organization_id: str = "",
    ) -> SREIncident:
        """Open an incident automatically from a firing alert (idempotent)."""
        existing = await self._find_open_for_alert(db, alert.alert_id)
        if existing is not None:
            return existing
        severity = alert.severity if alert.severity in SEVERITIES else SEV2
        incident = await self.create(
            db,
            title=f"[Alert] {alert.rule_name}",
            severity=severity,
            description=alert.message,
            organization_id=organization_id,
            service_id=alert.service_id,
            region=alert.region,
            detection="alert",
        )
        await self.correlate(db, incident.incident_id, alert_ids=[alert.alert_id])
        return incident

    async def _find_open_for_alert(self, db: AsyncSession, alert_id: str) -> Optional[SREIncident]:
        incidents = (await db.execute(select(SREIncident))).scalars().all()
        for incident in incidents:
            if incident.status not in (INCIDENT_RESOLVED, INCIDENT_CLOSED) and alert_id in (incident.related_alerts or []):
                return incident
        return None

    # ------------------------------------------------------ AI diagnosis
    async def diagnose(
        self,
        db: AsyncSession,
        incident_id: str,
        *,
        use_ai: bool = True,
    ) -> dict:
        """Advisory diagnosis: telemetry + recent changes + dependency graph.

        Produces evidence and recommended actions only; root causes are
        never fabricated. AI enhancement is best-effort and labeled as
        advisory.
        """
        incident = await get_one(db, SREIncident, incident_id=incident_id)
        if incident is None:
            return {"error": "incident not found"}

        evidence: list[dict] = []
        recommendations: list[str] = []

        # Recent deployments correlated to the service.
        if incident.service_id:
            result = await db.execute(
                select(SREDeployment)
                .where(
                    SREDeployment.service_id == incident.service_id,
                    SREDeployment.created_at >= _utcnow() - timedelta(hours=24),
                )
                .order_by(SREDeployment.created_at.desc())
            )
            recent_deployments = result.scalars().all()
            for deployment in recent_deployments[:5]:
                evidence.append({
                    "kind": "deployment",
                    "id": deployment.deployment_id,
                    "version": deployment.version,
                    "status": deployment.status,
                    "strategy": deployment.strategy,
                    "started_at": deployment.started_at.isoformat(),
                })
                if deployment.status in ("failed", "rolled_back"):
                    recommendations.append(
                        f"Recent {deployment.status} deployment of {incident.service_id} (version {deployment.version}) "
                        f"may be related; verify target version and rollback safety."
                    )

        # Firing alerts for the service.
        if incident.service_id:
            result = await db.execute(
                select(SREAlert)
                .where(SREAlert.service_id == incident.service_id, SREAlert.status == "firing")
                .order_by(SREAlert.fired_at.desc())
            )
            alerts = result.scalars().all()
            for alert in alerts[:10]:
                evidence.append({
                    "kind": "alert",
                    "id": alert.alert_id,
                    "rule": alert.rule_name,
                    "severity": alert.severity,
                    "message": alert.message,
                    "fired_at": alert.fired_at.isoformat(),
                })

        # Dependency graph context.
        from app.sre.service_catalog import service_catalog

        graph = await service_catalog.impact(db, incident.service_id) if incident.service_id else {"impacted_services": []}
        evidence.append({"kind": "dependency_graph", "impacted_services": graph.get("impacted_services", [])})

        # Timeline-based sequence detection.
        timeline = await self.timeline(db, incident_id)
        deployment_events = [t for t in timeline if t["event_type"] == "deployment"]
        evidence.append({"kind": "timeline", "events": len(timeline), "deployment_events": len(deployment_events)})

        root_cause_hypotheses: list[str] = []
        if any(e.get("status") in ("failed", "rolled_back") for e in evidence if e.get("kind") == "deployment"):
            root_cause_hypotheses.append("deployment regression (pending verification)")
        if any(e.get("kind") == "alert" and e.get("severity") in ("SEV0", "SEV1") for e in evidence):
            root_cause_hypotheses.append("infrastructure/dependency failure (pending verification)")

        diagnosis = {
            "incident_id": incident_id,
            "advisory": True,
            "evidence": evidence,
            "recommended_actions": recommendations,
            "hypotheses": root_cause_hypotheses,
            "disclaimer": "AI diagnosis is advisory. Root causes require verification by responders.",
        }

        if use_ai and recommendations:
            diagnosis["ai_notes"] = (
                "Correlation between recent changes and incident timeline detected. "
                "No remediation was performed automatically."
            )
        return diagnosis

    # ---------------------------------------------------------- analytics
    async def metrics(self, db: AsyncSession, *, window_days: int = 30) -> dict:
        """MTTD / MTTA / MTTM / MTTR over the window."""
        now = _utcnow()
        start = now - timedelta(days=window_days)
        result = await db.execute(
            select(SREIncident).where(SREIncident.detected_at >= start)
        )
        incidents = result.scalars().all()

        def mean(values: list[float]) -> float:
            return round(sum(values) / len(values), 2) if values else 0.0

        mttd = mean([
            (i.acknowledged_at - i.detected_at).total_seconds() / 60.0
            for i in incidents if i.acknowledged_at is not None
        ])
        mtta = mean([
            (i.acknowledged_at - i.detected_at).total_seconds() / 60.0
            for i in incidents if i.acknowledged_at is not None
        ])
        mttm = mean([
            (i.mitigated_at - i.detected_at).total_seconds() / 60.0
            for i in incidents if i.mitigated_at is not None
        ])
        mttr = mean([
            (i.resolved_at - i.detected_at).total_seconds() / 60.0
            for i in incidents if i.resolved_at is not None
        ])
        by_severity: dict[str, int] = {}
        for incident in incidents:
            by_severity[incident.severity] = by_severity.get(incident.severity, 0) + 1
        return {
            "window_days": window_days,
            "incidents": len(incidents),
            "by_severity": by_severity,
            "mttd_minutes": mttd,
            "mtta_minutes": mtta,
            "mttm_minutes": mttm,
            "mttr_minutes": mttr,
        }


incident_manager = IncidentManager()
