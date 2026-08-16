"""Reliability score (Volume 35).

An explainable, component-weighted reliability score built from
measurable signals:

  availability   - SLO availability compliance (0..1)
  latency        - latency SLO compliance (0..1)
  error_rate     - 1 - observed error rate (0..1)
  incident_freq  - inverse of incident frequency over the window
  recovery_time  - inverse of mean recovery time
  slo_compliance - share of SLOs in ok status
  dependency     - share of healthy dependencies
  cfr            - 1 - change failure rate (failed deployments / total)

The score is never fabricated: every component is derived from recorded
data and the breakdown is returned alongside the aggregate.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.models import (
    SREAlert,
    SREDeployment,
    SREDependencyHealth,
    SREErrorBudget,
    SREIncident,
    SRESLIMeasurement,
    SRESLO,
)
from app.sre.store import list_all

logger = logging.getLogger(__name__)

WEIGHTS: dict[str, float] = {
    "availability": 0.20,
    "latency": 0.10,
    "error_rate": 0.15,
    "slo_compliance": 0.15,
    "incident_frequency": 0.10,
    "recovery_time": 0.10,
    "dependency_health": 0.10,
    "change_failure_rate": 0.10,
}


class ReliabilityScoreEngine:
    """Computes explainable reliability scores from recorded signals."""

    async def score(
        self,
        db: AsyncSession,
        *,
        service_id: Optional[str] = None,
        window_days: int = 30,
        now: Optional[datetime] = None,
    ) -> dict:
        now = now or datetime.now(timezone.utc)
        start = now - timedelta(days=window_days)

        components: dict[str, float] = {}
        details: dict[str, str] = {}

        # ------------------------------------------------- availability
        availability = await self._slo_component(db, service_id, "availability", start)
        components["availability"] = availability["value"]
        details["availability"] = availability["explanation"]

        # ------------------------------------------------- latency
        latency = await self._slo_component(db, service_id, "latency", start)
        components["latency"] = latency["value"]
        details["latency"] = latency["explanation"]

        # ------------------------------------------------- error rate
        error_rate = await self._error_rate(db, service_id, start)
        components["error_rate"] = error_rate["value"]
        details["error_rate"] = error_rate["explanation"]

        # ------------------------------------------------- SLO compliance
        slo_compliance = await self._slo_compliance(db, service_id, start)
        components["slo_compliance"] = slo_compliance["value"]
        details["slo_compliance"] = slo_compliance["explanation"]

        # ------------------------------------------------- incident frequency
        incidents = await self._count(db, SREIncident, service_id, start)
        freq_score = max(0.0, 1.0 - (incidents / max(1.0, window_days / 7.0)) * 0.25)
        components["incident_frequency"] = round(freq_score, 4)
        details["incident_frequency"] = f"{incidents} incidents in {window_days} days (expected <= 1/week)"

        # ------------------------------------------------- recovery time
        recovery = await self._recovery_time(db, service_id, start)
        components["recovery_time"] = recovery["value"]
        details["recovery_time"] = recovery["explanation"]

        # ------------------------------------------------- dependency health
        dependency = await self._dependency_health(db)
        components["dependency_health"] = dependency["value"]
        details["dependency_health"] = dependency["explanation"]

        # ------------------------------------------------- change failure rate
        cfr = await self._change_failure_rate(db, service_id, start)
        components["change_failure_rate"] = cfr["value"]
        details["change_failure_rate"] = cfr["explanation"]

        weighted = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)
        score = round(min(1.0, max(0.0, weighted)) * 100.0, 2)

        grade = "A" if score >= 95 else "B" if score >= 85 else "C" if score >= 75 else "D" if score >= 60 else "F"
        return {
            "service_id": service_id or "platform",
            "window_days": window_days,
            "score": score,
            "grade": grade,
            "components": {k: round(v, 4) for k, v in components.items()},
            "weights": WEIGHTS,
            "explanations": details,
        }

    async def _slo_component(
        self, db: AsyncSession, service_id: Optional[str], sli_type: str, start: datetime
    ) -> dict:
        # Error budgets do not carry sli_type; join through SLOs.
        stmt = (
            select(SRESLO, SREErrorBudget)
            .join(SREErrorBudget, SREErrorBudget.slo_id == SRESLO.slo_id)
            .where(SRESLO.sli_type == sli_type, SREErrorBudget.computed_at >= start)
        )
        if service_id:
            stmt = stmt.where(SRESLO.service_id == service_id)
        rows = (await db.execute(stmt)).all()
        if not rows:
            return {"value": 1.0, "explanation": f"no {sli_type} SLO data recorded; defaulting to 1.0"}
        ok = sum(1 for _, budget in rows if budget.status == "healthy")
        value = ok / len(rows)
        return {"value": round(value, 4), "explanation": f"{ok}/{len(rows)} {sli_type} budgets healthy in window"}

    async def _error_rate(self, db: AsyncSession, service_id: Optional[str], start: datetime) -> dict:
        stmt = select(SRESLIMeasurement).where(SRESLIMeasurement.sli_type == "availability", SRESLIMeasurement.bucket_start >= start)
        if service_id:
            stmt = stmt.where(SRESLIMeasurement.service_id == service_id)
        rows = (await db.execute(stmt)).scalars().all()
        total = sum(r.total for r in rows)
        good = sum(r.good for r in rows)
        if total <= 0:
            return {"value": 1.0, "explanation": "no availability measurements in window"}
        value = good / total
        return {"value": round(value, 4), "explanation": f"successful={good:.0f} total={total:.0f} requests"}

    async def _slo_compliance(self, db: AsyncSession, service_id: Optional[str], start: datetime) -> dict:
        stmt = select(SREErrorBudget).where(SREErrorBudget.computed_at >= start)
        if service_id:
            stmt = stmt.where(SREErrorBudget.service_id == service_id)
        rows = (await db.execute(stmt)).scalars().all()
        if not rows:
            return {"value": 1.0, "explanation": "no SLO snapshots in window"}
        ok = sum(1 for r in rows if r.status == "healthy")
        return {"value": round(ok / len(rows), 4), "explanation": f"{ok}/{len(rows)} SLO snapshots healthy"}

    async def _count(self, db: AsyncSession, model, service_id: Optional[str], start: datetime) -> int:
        stmt = select(func.count()).select_from(model)
        filters = []
        if service_id and hasattr(model, "service_id"):
            filters.append(model.service_id == service_id)
        if hasattr(model, "detected_at"):
            filters.append(model.detected_at >= start)
        elif hasattr(model, "created_at"):
            filters.append(model.created_at >= start)
        result = await db.execute(stmt.where(*filters))
        return int(result.scalar() or 0)

    async def _recovery_time(self, db: AsyncSession, service_id: Optional[str], start: datetime) -> dict:
        stmt = select(SREIncident).where(
            SREIncident.resolved_at.is_not(None),
            SREIncident.detected_at >= start,
        )
        if service_id:
            stmt = stmt.where(SREIncident.service_id == service_id)
        incidents = (await db.execute(stmt)).scalars().all()
        if not incidents:
            return {"value": 1.0, "explanation": "no resolved incidents in window"}
        durations = [
            max((i.resolved_at - i.detected_at).total_seconds() / 60.0, 0.0)
            for i in incidents
            if i.resolved_at is not None
        ]
        mean_minutes = sum(durations) / len(durations)
        # Score degrades from 1.0 at <5min to 0.0 at >=120min mean recovery.
        value = max(0.0, 1.0 - (mean_minutes - 5.0) / 115.0)
        return {"value": round(value, 4), "explanation": f"mean time to resolve {mean_minutes:.0f} minutes"}

    async def _dependency_health(self, db: AsyncSession) -> dict:
        rows = (await db.execute(select(SREDependencyHealth))).scalars().all()
        if not rows:
            return {"value": 1.0, "explanation": "no dependency health data recorded"}
        ok = sum(1 for r in rows if r.status in ("healthy", "unknown"))
        return {"value": round(ok / len(rows), 4), "explanation": f"{ok}/{len(rows)} dependencies healthy"}

    async def _change_failure_rate(self, db: AsyncSession, service_id: Optional[str], start: datetime) -> dict:
        stmt = select(SREDeployment).where(
            SREDeployment.created_at >= start,
            SREDeployment.status.in_(["success", "failed", "rolled_back"]),
        )
        if service_id:
            stmt = stmt.where(SREDeployment.service_id == service_id)
        deployments = (await db.execute(stmt)).scalars().all()
        if not deployments:
            return {"value": 1.0, "explanation": "no completed deployments in window"}
        failed = sum(1 for d in deployments if d.status != "success")
        value = 1.0 - (failed / len(deployments))
        return {"value": round(value, 4), "explanation": f"{failed}/{len(deployments)} deployments failed"}


reliability_engine = ReliabilityScoreEngine()
