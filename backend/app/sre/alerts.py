"""Alert lifecycle and rule evaluation (Volume 35).

Alerts are deduplicated per (rule_name, service_id, region): a firing
alert is not duplicated by repeated evaluation of the same condition
(idempotent). Alert resolution is explicit via resolve_alert or the
monitoring workers.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import (
    ALERT_STATUS_ACKED,
    ALERT_STATUS_FIRING,
    ALERT_STATUS_RESOLVED,
    SEV2,
    SEVERITIES,
    SEVERITY_RANK,
)
from app.sre.models import SREAlert
from app.sre.store import new_key

logger = logging.getLogger(__name__)


async def create_alert(
    db: AsyncSession,
    *,
    rule_name: str,
    severity: str = SEV2,
    message: str = "",
    service_id: str = "",
    region: str = "",
    metadata_json: Optional[dict] = None,
) -> SREAlert:
    """Create an alert, deduplicating against an already-firing alert with
    the same (rule_name, service_id, region)."""
    existing = await _find_firing(db, rule_name, service_id, region)
    if existing is not None:
        if message and message != existing.message:
            existing.metadata_json = {**(existing.metadata_json or {}), "updated_message": message}
            await db.flush()
        return existing
    alert = SREAlert(
        alert_id=new_key("alert"),
        rule_name=rule_name,
        severity=severity,
        service_id=service_id,
        region=region,
        message=message,
        status=ALERT_STATUS_FIRING,
        metadata_json=metadata_json or {},
    )
    db.add(alert)
    await db.flush()
    return alert


async def _find_firing(db: AsyncSession, rule_name: str, service_id: str, region: str) -> Optional[SREAlert]:
    result = await db.execute(
        select(SREAlert).where(
            SREAlert.rule_name == rule_name,
            SREAlert.service_id == service_id,
            SREAlert.region == region,
            SREAlert.status.in_((ALERT_STATUS_FIRING, ALERT_STATUS_ACKED)),
        )
    )
    return result.scalar_one_or_none()


async def acknowledge_alert(db: AsyncSession, alert_id: str) -> Optional[SREAlert]:
    alert = await db.get(SREAlert, alert_id)
    if alert is None or alert.status == ALERT_STATUS_RESOLVED:
        return None
    alert.status = ALERT_STATUS_ACKED
    alert.metadata_json = {**(alert.metadata_json or {}), "acknowledged_at": datetime.now(timezone.utc).isoformat()}
    await db.flush()
    return alert


async def resolve_alert(db: AsyncSession, alert_id: str) -> Optional[SREAlert]:
    alert = await db.get(SREAlert, alert_id)
    if alert is None:
        return None
    if alert.status != ALERT_STATUS_RESOLVED:
        alert.status = ALERT_STATUS_RESOLVED
        alert.resolved_at = datetime.now(timezone.utc)
        await db.flush()
    return alert


async def resolve_by_rule(db: AsyncSession, rule_name: str, service_id: str = "", region: str = "") -> int:
    """Resolve all firing alerts for a rule (used when conditions recover)."""
    stmt = select(SREAlert).where(
        SREAlert.rule_name == rule_name,
        SREAlert.status.in_((ALERT_STATUS_FIRING, ALERT_STATUS_ACKED)),
    )
    if service_id:
        stmt = stmt.where(SREAlert.service_id == service_id)
    if region:
        stmt = stmt.where(SREAlert.region == region)
    alerts = list((await db.execute(stmt)).scalars().all())
    for alert in alerts:
        alert.status = ALERT_STATUS_RESOLVED
        alert.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return len(alerts)


async def list_alerts(
    db: AsyncSession,
    *,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    service_id: Optional[str] = None,
    region: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[dict], int]:
    stmt = select(SREAlert)
    if status:
        stmt = stmt.where(SREAlert.status == status)
    if severity:
        stmt = stmt.where(SREAlert.severity == severity)
    if service_id:
        stmt = stmt.where(SREAlert.service_id == service_id)
    if region:
        stmt = stmt.where(SREAlert.region == region)
    total = len(list((await db.execute(stmt)).scalars().all()))
    stmt = stmt.order_by(SREAlert.fired_at.desc()).offset(offset).limit(limit)
    alerts = list((await db.execute(stmt)).scalars().all())
    return [alert.to_dict() for alert in alerts], total


def severity_valid(severity: str) -> bool:
    return severity in SEVERITIES


def severity_escalates(current: Optional[str], incoming: str) -> bool:
    """True when incoming severity is more severe than the current alert's."""
    if current is None or current not in SEVERITY_RANK:
        return True
    return SEVERITY_RANK[incoming] < SEVERITY_RANK[current]