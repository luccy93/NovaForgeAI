"""Incident management (Volume 35).

Structured incident lifecycle with a validated state machine, automatic
timeline recording, incident command roles, correlation with
deployments/changes/alerts, AI-assisted diagnosis (advisory only), and
blame-free postmortems with corrective-action tracking.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import (
    INCIDENT_ACTIVE_STATUSES,
    INCIDENT_DETECTED,
    INCIDENT_INVESTIGATING,
    INCIDENT_STATUSES,
    INCIDENT_TRANSITIONS,
    SEV1,
    SEV0,
    SEVERITIES,
)
from app.sre.models import (
    SREAlert,
    SRECorrectiveAction,
    SREDeployment,
    SREIncident,
    SREIncidentEvent,
    SREIncidentResponder,
    SREPostmortem,
)
from app.sre.store import new_id, new_key

logger = logging.getLogger(__name__)


class InvalidTransitionError(ValueError):
    pass


def validate_transition(current: str, target: str) -> None:
    if current not in INCIDENT_STATUSES or target not in INCIDENT_STATUSES:
        raise InvalidTransitionError(f"invalid incident status: {current} -> {target}")
    if current not in INCIDENT_TRANSITIONS:
        raise InvalidTransitionError(f"unknown status {current}")
    if target not in INCIDENT_TRANSITIONS[current]:
        raise InvalidTransitionError(f"invalid incident transition: {current} -> {target}")


def validate_severity(severity: str) -> bool:
    return severity in SEVERITIES


async def create_incident(
    db: AsyncSession,
    *,
    title: str,
    description: str = "",
    severity: str = SEV1,
    service_id: str = "",
    region: str = "",
    organization_id: str = "",
    detection: str = "alert",
    commander: str = "",
    related_alerts: Optional[list] = None,
    related_deployments: Optional[list] = None,
    related_changes: Optional[list] = None,
    impact: Optional[dict] = None,
) -> SREIncident:
    incident = SREIncident(
        incident_id=new_key("incident"),
        organization_id=organization_id,
        title=title,
        description=description,
        severity=severity if validate_severity(severity) else SEV1,
        status=INCIDENT_DETECTED,
        service_id=service_id,
        region=region,
        commander=commander,
        detection=detection,
        related_alerts=related_alerts or [],
        related_deployments=related_deployments or [],
        related_changes=related_changes or [],
        impact=impact or {},
    )
    db.add(incident)
    await db.flush()
    await add_event(db, incident.incident_id, "alert", actor="system", message=f"Incident created via {detection}")
    return incident


async def add_event(
    db: AsyncSession,
    incident_id: str,
    event_type: str,
    *,
    actor: str = "system",
    message: str = "",
    metadata_json: Optional[dict] = None,
) -> SREIncidentEvent:
    event = SREIncidentEvent(
        incident_id=incident_id,
        event_type=event_type,
        actor=actor,
        message=message,
        metadata_json=metadata_json or {},
    )
    db.add(event)
    await db.flush()
    return event


async def transition(
    db: AsyncSession,
    incident: SREIncident,
    target: str,
    *,
    actor: str = "system",
    note: str = "",
) -> SREIncident:
    """Move an incident through the state machine, stamping lifecycle
    timestamps and appending timeline events."""
    validate_transition(incident.status, target)
    incident.status = target
    now = datetime.now(timezone.utc)
    if target == INCIDENT_INVESTIGATING:
        incident.acknowledged_at = incident.acknowledged_at or now
    if target == "mitigating":
        incident.mitigated_at = incident.mitigated_at or now
    if target == "resolved":
        incident.resolved_at = now
    if target == "closed":
        incident.closed_at = now
    await db.flush()
    await add_event(db, incident.incident_id, target, actor=actor, message=note or f"status -> {target}")
    return incident


async def assign_responder(db: AsyncSession, incident_id: str, role: str, user_id: str) -> SREIncidentResponder:
    responder = SREIncidentResponder(incident_id=incident_id, role=role, user_id=user_id)
    db.add(responder)
    await db.flush()
    return responder


# ---------------------------------------------------------------------------
# Incident correlation
# ---------------------------------------------------------------------------

async def correlate_recent_changes(db: AsyncSession, incident: SREIncident, *, hours: int = 24) -> list[dict]:
    """Identify recent deployments/changes that could relate to the incident."""
    since = datetime.now(timezone.utc).timestamp() - hours * 3600
    since_dt = datetime.fromtimestamp(since, tz=timezone.utc)
    stmt = select(SREDeployment).where(SREDeployment.started_at >= since_dt)
    if incident.service_id:
        stmt = stmt.where(SREDeployment.service_id == incident.service_id)
    deployments = list((await db.execute(stmt)).scalars().all())
    related = []
    for deployment in deployments:
        related.append(
            {
                "kind": "deployment",
                "id": deployment.deployment_id,
                "service_id": deployment.service_id,
                "version": deployment.version,
                "commit": deployment.commit,
                "status": deployment.status,
                "started_at": deployment.started_at.isoformat() if deployment.started_at else None,
            }
        )
    if related:
        incident.related_deployments = [d["id"] for d in related]
        await db.flush()
    return related


async def correlate_alerts(db: AsyncSession, incident: SREIncident, *, hours: int = 6) -> list[dict]:
    since = datetime.now(timezone.utc).timestamp() - hours * 3600
    since_dt = datetime.fromtimestamp(since, tz=timezone.utc)
    stmt = select(SREAlert).where(SREAlert.fired_at >= since_dt)
    if incident.service_id:
        stmt = stmt.where(SREAlert.service_id == incident.service_id)
    alerts = list((await db.execute(stmt)).scalars().all())
    related = [{"id": a.alert_id, "rule_name": a.rule_name, "severity": a.severity, "status": a.status} for a in alerts]
    if related:
        incident.related_alerts = [a["id"] for a in related]
        await db.flush()
    return related


# ---------------------------------------------------------------------------
# AI-assisted diagnosis (advisory only - never fabricates root causes)
# ---------------------------------------------------------------------------

async def ai_diagnosis(db: AsyncSession, incident: SREIncident, *, recent_changes: Optional[list] = None) -> dict:
    """Produce an advisory diagnosis from available evidence.

    The diagnosis is explicitly marked advisory: no automated remediation
    is performed from this output and no root cause is claimed without
    evidence. If the AI agents are unavailable this returns a structured
    evidence summary instead of hallucinated analysis.
    """
    changes = recent_changes if recent_changes is not None else await correlate_recent_changes(db, incident)
    alerts = await correlate_alerts(db, incident)
    evidence = {
        "incident": incident.title,
        "severity": incident.severity,
        "service": incident.service_id,
        "region": incident.region,
        "detection": incident.detection,
        "related_alerts": alerts,
        "related_changes": changes,
    }
    recommendations = []
    if incident.service_id:
        recommendations.append(f"Consult the runbook for service {incident.service_id}")
    for change in changes:
        if change["status"] == "in_progress":
            recommendations.append(f"Review in-progress deployment {change['id']} - candidate rollback target")
    for alert in alerts:
        if alert["status"] in ("firing", "acked"):
            recommendations.append(f"Verify alert {alert['rule_name']} (severity {alert['severity']})")
    return {
        "advisory": True,
        "disclaimer": "AI diagnosis is advisory. Root cause must be confirmed from evidence before remediation.",
        "evidence": evidence,
        "recommendations": recommendations,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Postmortems & corrective actions
# ---------------------------------------------------------------------------

async def create_postmortem(
    db: AsyncSession,
    *,
    incident: SREIncident,
    summary: str,
    impact: str = "",
    root_cause: str = "",
    contributing_factors: Optional[list] = None,
    detection: str = "",
    response: str = "",
    what_went_well: Optional[list] = None,
    what_went_wrong: Optional[list] = None,
    created_by: str = "system",
) -> SREPostmortem:
    timeline = [event.to_dict() for event in (await get_timeline(db, incident.incident_id))]
    postmortem = SREPostmortem(
        postmortem_id=new_key("postmortem"),
        incident_id=incident.incident_id,
        summary=summary,
        impact=impact,
        timeline=timeline,
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


async def create_corrective_action(
    db: AsyncSession,
    *,
    description: str,
    incident_id: str = "",
    postmortem_id: str = "",
    owner: str = "",
    priority: str = "medium",
    due_date: Optional[datetime] = None,
) -> SRECorrectiveAction:
    action = SRECorrectiveAction(
        action_id=new_key("action"),
        incident_id=incident_id,
        postmortem_id=postmortem_id,
        description=description,
        owner=owner,
        priority=priority,
        due_date=due_date,
    )
    db.add(action)
    await db.flush()
    return action


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

async def get_timeline(db: AsyncSession, incident_id: str) -> list[SREIncidentEvent]:
    result = await db.execute(
        select(SREIncidentEvent).where(SREIncidentEvent.incident_id == incident_id).order_by(SREIncidentEvent.occurred_at)
    )
    return list(result.scalars().all())


async def list_incidents(
    db: AsyncSession,
    *,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    service_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[dict], int]:
    stmt = select(SREIncident)
    conditions = []
    if status:
        conditions.append(SREIncident.status == status)
    if severity:
        conditions.append(SREIncident.severity == severity)
    if service_id:
        conditions.append(SREIncident.service_id == service_id)
    if organization_id:
        conditions.append(SREIncident.organization_id == organization_id)
    for condition in conditions:
        stmt = stmt.where(condition)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.order_by(SREIncident.detected_at.desc()).offset(offset).limit(limit)
    incidents = list((await db.execute(stmt)).scalars().all())
    return [incident.to_dict() for incident in incidents], total


def incident_is_active(status: str) -> bool:
    return status in INCIDENT_ACTIVE_STATUSES


def require_incident(incident: Optional[SREIncident]) -> SREIncident:
    if incident is None:
        raise InvalidTransitionError("incident not found")
    return incident