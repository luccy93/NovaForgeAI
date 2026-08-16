"""SRE reports (Volume 35).

Report generation over real measurements - daily / weekly / monthly
reliability reports, incident reports, service health, SLO, capacity,
disaster-recovery and dependency reports. All numbers come from the
operational tables.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.models import (
    SREAlert,
    SRECapacityMetric,
    SREDeployment,
    SREDependencyHealth,
    SREIncident,
    SRERegionHealth,
    SREReport,
    SRERestoreTest,
    SREFailoverTest,
)
from app.sre.store import new_key

logger = logging.getLogger(__name__)

REPORT_KINDS = ("daily", "weekly", "monthly", "incident", "service_health", "slo", "capacity", "dr", "dependency")


async def generate_daily_reports(db: AsyncSession, *, now: Optional[datetime] = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    window = now - timedelta(days=30)
    report_ids = []
    for kind in ("daily", "weekly", "service_health", "slo", "capacity", "dr", "dependency"):
        try:
            report = await build_report(db, kind=kind, period_start=window, period_end=now)
            report_ids.append(report)
        except Exception as exc:  # a failing report must not break the batch
            logger.warning("report %s generation failed: %s", kind, exc)
    return report_ids


async def build_report(
    db: AsyncSession,
    *,
    kind: str,
    period_start: datetime,
    period_end: datetime,
    service_id: str = "",
) -> str:
    """Build and persist a report. Returns the report id."""
    data = await _collect(db, kind, period_start, period_end, service_id)
    report_id = new_key("report")
    title = f"{kind.replace('_', ' ').title()} Reliability Report"
    report = SREReport(
        report_id=report_id,
        kind=kind,
        title=title,
        period_start=period_start,
        period_end=period_end,
        data=data,
    )
    db.add(report)
    await db.flush()
    return report_id


async def _collect(db: AsyncSession, kind: str, start: datetime, end: datetime, service_id: str) -> dict:
    if kind == "incident":
        return await _incident_report(db, start, end, service_id)
    if kind == "service_health":
        return await _service_health_report(db, start, end, service_id)
    if kind == "slo":
        return await _slo_report(db, start, end, service_id)
    if kind == "capacity":
        return await _capacity_report(db, start, end, service_id)
    if kind == "dr":
        return await _dr_report(db, start, end, service_id)
    if kind == "dependency":
        return await _dependency_report(db, start, end, service_id)
    return await _reliability_report(db, start, end, service_id)


async def _reliability_report(db: AsyncSession, start: datetime, end: datetime, service_id: str) -> dict:
    incident_stmt = select(SREIncident).where(SREIncident.detected_at >= start, SREIncident.detected_at <= end)
    deployment_stmt = select(SREDeployment).where(SREDeployment.started_at >= start, SREDeployment.started_at <= end)
    if service_id:
        incident_stmt = incident_stmt.where(SREIncident.service_id == service_id)
        deployment_stmt = deployment_stmt.where(SREDeployment.service_id == service_id)
    incidents = list((await db.execute(incident_stmt)).scalars().all())
    deployments = list((await db.execute(deployment_stmt)).scalars().all())

    resolved = [i for i in incidents if i.resolved_at and i.detected_at]
    mttr = None
    if resolved:
        minutes = [(i.resolved_at - i.detected_at).total_seconds() / 60 for i in resolved]
        mttr = round(sum(minutes) / len(minutes), 2)

    failed_deployments = [d for d in deployments if d.status == "failed"]
    rolled_back = [d for d in deployments if d.status == "rolled_back"]
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "service_id": service_id,
        "incidents": {"total": len(incidents), "open": sum(1 for i in incidents if i.status not in ("resolved", "closed"))},
        "mttd_hours": None,
        "mtta_hours": None,
        "mttm_hours": None,
        "mttr_minutes": mttr,
        "deployments": {
            "total": len(deployments),
            "failed": len(failed_deployments),
            "rolled_back": len(rolled_back),
            "change_failure_rate": round(len(failed_deployments) / len(deployments), 4) if deployments else 0.0,
            "deployment_frequency_per_day": round(len(deployments) / max((end - start).days, 1), 2),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _incident_report(db: AsyncSession, start: datetime, end: datetime, service_id: str) -> dict:
    stmt = select(SREIncident).where(SREIncident.detected_at >= start, SREIncident.detected_at <= end)
    if service_id:
        stmt = stmt.where(SREIncident.service_id == service_id)
    incidents = list((await db.execute(stmt)).scalars().all())
    by_severity: dict[str, int] = {}
    for incident in incidents:
        by_severity[incident.severity] = by_severity.get(incident.severity, 0) + 1
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "incidents": [i.to_dict() for i in incidents],
        "count": len(incidents),
        "by_severity": by_severity,
    }


async def _service_health_report(db: AsyncSession, start: datetime, end: datetime, service_id: str) -> dict:
    alert_stmt = select(SREAlert).where(SREAlert.fired_at >= start, SREAlert.fired_at <= end)
    dep_stmt = select(SREDependencyHealth).where(SREDependencyHealth.measured_at >= start)
    if service_id:
        alert_stmt = alert_stmt.where(SREAlert.service_id == service_id)
        dep_stmt = dep_stmt.where(SREDependencyHealth.dependency == service_id)
    alerts = list((await db.execute(alert_stmt)).scalars().all())
    deps = list((await db.execute(dep_stmt)).scalars().all())
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "alerts": {"total": len(alerts), "firing": sum(1 for a in alerts if a.status == "firing"), "acked": sum(1 for a in alerts if a.status == "acked")},
        "dependencies": {"samples": len(deps), "last_status": deps[-1].to_dict() if deps else None},
    }


async def _slo_report(db: AsyncSession, start: datetime, end: datetime, service_id: str) -> dict:
    from app.sre.models import SREErrorBudget, SRESLO

    stmt = select(SRESLO)
    if service_id:
        stmt = stmt.where(SRESLO.service_id == service_id)
    slos = list((await db.execute(stmt)).scalars().all())
    result = []
    for slo in slos:
        budget_stmt = (
            select(SREErrorBudget)
            .where(SREErrorBudget.slo_id == slo.slo_id, SREErrorBudget.computed_at >= start)
            .order_by(SREErrorBudget.computed_at.desc())
        )
        budget = (await db.execute(budget_stmt)).scalar_one_or_none()
        result.append(
            {
                "slo_id": slo.slo_id,
                "name": slo.name,
                "target": slo.target,
                "sli_type": slo.sli_type,
                "window": slo.window,
                "status": budget.status if budget else "no_data",
                "consumed_percent": budget.consumed_percent if budget else None,
                "burn_rate": budget.burn_rate if budget else None,
            }
        )
    return {"period": {"start": start.isoformat(), "end": end.isoformat()}, "slos": result}


async def _capacity_report(db: AsyncSession, start: datetime, end: datetime, service_id: str) -> dict:
    stmt = select(
        SRECapacityMetric.service_id,
        SRECapacityMetric.metric,
        func.max(SRECapacityMetric.value),
        func.avg(SRECapacityMetric.value),
        func.count(),
    ).where(SRECapacityMetric.measured_at >= start, SRECapacityMetric.measured_at <= end)
    if service_id:
        stmt = stmt.where(SRECapacityMetric.service_id == service_id)
    stmt = stmt.group_by(SRECapacityMetric.service_id, SRECapacityMetric.metric)
    rows = list((await db.execute(stmt)).all())
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "metrics": [
            {"service_id": row[0], "metric": row[1], "peak": round(float(row[2] or 0), 2), "average": round(float(row[3] or 0), 2), "samples": int(row[4] or 0)}
            for row in rows
        ],
    }


async def _dr_report(db: AsyncSession, start: datetime, end: datetime, service_id: str) -> dict:
    restore_stmt = select(SRERestoreTest).where(SRERestoreTest.created_at >= start, SRERestoreTest.created_at <= end)
    failover_stmt = select(SREFailoverTest).where(SREFailoverTest.created_at >= start, SREFailoverTest.created_at <= end)
    restore_tests = list((await db.execute(restore_stmt)).scalars().all())
    failover_tests = list((await db.execute(failover_stmt)).scalars().all())
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "restore_tests": {"total": len(restore_tests), "passed": sum(1 for t in restore_tests if t.integrity and t.completeness and t.consistency), "failed": sum(1 for t in restore_tests if t.status == "failed")},
        "failover_tests": {"total": len(failover_tests), "passed": sum(1 for t in failover_tests if t.passed), "failed": sum(1 for t in failover_tests if t.status == "failed")},
    }


async def _dependency_report(db: AsyncSession, start: datetime, end: datetime, service_id: str) -> dict:
    stmt = select(SREDependencyHealth).where(SREDependencyHealth.measured_at >= start, SREDependencyHealth.measured_at <= end)
    rows = list((await db.execute(stmt)).scalars().all())
    latest: dict[str, dict] = {}
    for row in rows:
        latest.setdefault(row.dependency, row.to_dict())
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "dependencies": [latest[key] for key in sorted(latest)],
    }


async def list_reports(db: AsyncSession, *, kind: str = "", offset: int = 0, limit: int = 50) -> tuple[list[dict], int]:
    stmt = select(SREReport)
    if kind:
        stmt = stmt.where(SREReport.kind == kind)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.order_by(SREReport.created_at.desc()).offset(offset).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return [row.to_dict() for row in rows], total