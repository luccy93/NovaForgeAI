"""SRE reports (Volume 35).

Generates and stores reliability reports: daily, weekly, monthly SRE
reports, incident reports, service health, SLO, capacity, disaster
recovery, and dependency reports.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.models import SREReport
from app.sre.store import get_one, list_all, new_id, new_key

logger = logging.getLogger(__name__)

REPORT_KINDS = ["daily", "weekly", "monthly", "incident", "service_health", "slo", "capacity", "dr", "dependency"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReportEngine:
    """Builds reliability reports from live SRE data."""

    async def generate(
        self,
        db: AsyncSession,
        *,
        kind: str,
        days: int = 7,
        service_id: str = "",
        incident_id: str = "",
        now: Optional[datetime] = None,
    ) -> dict:
        if kind not in REPORT_KINDS:
            raise ValueError(f"unknown report kind: {kind}")
        now = now or _utcnow()
        period_start = now - timedelta(days=days)

        from app.sre.incident import incident_manager
        from app.sre.reliability import reliability_engine
        from app.sre.slo import slo_engine

        data: dict = {}
        if kind in ("daily", "weekly", "monthly"):
            data = await self._periodic_report(db, now, period_start, service_id)
        elif kind == "incident":
            data = await self._incident_report(db, incident_id) if incident_id else {
                "error": "incident_id required for incident report"
            }
        elif kind == "service_health":
            data = await self._service_health(db, service_id)
        elif kind == "slo":
            data = await self._slo_report(db, service_id)
        elif kind == "capacity":
            from app.sre.capacity import capacity_engine

            data = await capacity_engine.plan(db, service_id=service_id)
        elif kind == "dr":
            from app.sre.recovery import dr_manager

            data = await dr_manager.plan(db)
        elif kind == "dependency":
            from app.sre.dependencies import dependency_monitor

            data = {"dependencies": await dependency_monitor.status_map(db)}

        report = SREReport(
            id=new_id(),
            report_id=new_key("report"),
            kind=kind,
            title=f"{kind.title()} Reliability Report",
            period_start=period_start,
            period_end=now,
            data=data,
        )
        db.add(report)
        await db.flush()
        return report.to_dict()

    async def _periodic_report(self, db: AsyncSession, now: datetime, start: datetime, service_id: str) -> dict:
        from app.sre.incident import incident_manager
        from app.sre.reliability import reliability_engine

        incidents = await incident_manager.metrics(db, window_days=max(1, (now - start).days))
        score = await reliability_engine.score(db, service_id=service_id or None, window_days=max(1, (now - start).days), now=now)
        active = await incident_manager.active(db)
        from app.sre.deployments import deployment_reliability

        deployment_metrics = await deployment_reliability.metrics(db, window_days=max(1, (now - start).days))
        return {
            "incidents": incidents,
            "active_incidents": len(active),
            "reliability_score": score,
            "deployments": deployment_metrics,
            "generated_at": now.isoformat(),
        }

    async def _incident_report(self, db: AsyncSession, incident_id: str) -> dict:
        from app.sre.incident import incident_manager

        incident = await incident_manager.get(db, incident_id)
        if incident is None:
            return {"error": f"incident not found: {incident_id}"}
        diagnosis = await incident_manager.diagnose(db, incident_id, use_ai=False)
        return {"incident": incident, "diagnosis": diagnosis}

    async def _service_health(self, db: AsyncSession, service_id: str) -> dict:
        from app.sre.health import health_checker

        dependencies = await health_checker.dependencies()
        return {
            "service_id": service_id,
            "dependencies": dependencies,
            "generated_at": _utcnow().isoformat(),
        }

    async def _slo_report(self, db: AsyncSession, service_id: str) -> dict:
        from app.sre.slo import slo_engine
        from sqlalchemy import select

        from app.sre.models import SRESLO

        stmt = select(SRESLO).where(SRESLO.status == "active")
        if service_id:
            stmt = stmt.where(SRESLO.service_id == service_id)
        slos = (await db.execute(stmt)).scalars().all()
        evaluations = []
        for slo in slos:
            report = await slo_engine.evaluate(db, slo)
            evaluations.append(report)
        return {"slos": evaluations, "count": len(evaluations)}

    async def list(self, db: AsyncSession, *, kind: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        items, total = await list_all(
            db, SREReport, limit=limit, offset=offset, order_by="created_at", kind=kind
        )
        return [r.to_dict() for r in items], total

    async def get(self, db: AsyncSession, report_id: str) -> Optional[dict]:
        report = await get_one(db, SREReport, report_id=report_id)
        return report.to_dict() if report else None


report_engine = ReportEngine()