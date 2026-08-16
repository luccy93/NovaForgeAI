"""SRE background workers (Volume 35).

Periodic asyncio loops for: SLO/error-budget calculation, burn-rate alert
evaluation, dependency-health monitoring, certificate monitoring,
capacity forecasting warnings, incident correlation and report
generation.

Workers are isolated (one failure never kills the loop), idempotent and
driven by the existing async DB session factory. They are started from
the FastAPI lifespan.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.core.database import get_db_context
from app.sre.constants import BUDGET_EXHAUSTED, BURN_TIERS, CAPACITY_ALERT_THRESHOLD_PERCENT, CERT_EXPIRING
from app.sre import events as sre_events
from app.sre.alerts import create_alert, resolve_by_rule
from app.sre.metrics import set_dependency_status
from app.sre.models import SRESLO
from app.sre import slo as slo_service
from app.sre.slo import compute_all_budgets

logger = logging.getLogger(__name__)


def _interval(name: str, default: int) -> int:
    return max(10, int(os.getenv(f"SRE_WORKER_{name.upper()}_SECONDS", str(default))))


class SREWorkers:
    """Registry of background SRE worker loops."""

    def __init__(self) -> None:
        self._tasks: list[asyncio.Task] = []
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks = [
            asyncio.create_task(self._run("slo", self._loop_slo, _interval("SLO", 300))),
            asyncio.create_task(self._run("burn_rate", self._loop_burn_rate, _interval("BURN", 60))),
            asyncio.create_task(self._run("dependencies", self._loop_dependencies, _interval("DEPS", 60))),
            asyncio.create_task(self._run("certificates", self._loop_certificates, _interval("CERT", 3600))),
            asyncio.create_task(self._run("capacity", self._loop_capacity, _interval("CAPACITY", 600))),
            asyncio.create_task(self._run("reports", self._loop_reports, _interval("REPORTS", 3600))),
        ]
        logger.info("started %d SRE workers", len(self._tasks))

    async def stop(self) -> None:
        if not self._running and not self._tasks:
            return
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        logger.info("stopped all SRE workers")

    async def _run(self, name: str, coro, interval_seconds: int) -> None:
        while self._running:
            started = asyncio.get_event_loop().time()
            try:
                await coro()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # isolated: one worker failure must not stop the loop
                logger.exception("SRE worker %s failed: %s", name, exc)
            elapsed = asyncio.get_event_loop().time() - started
            await asyncio.sleep(max(interval_seconds - elapsed, 1))

    # ------------------------------------------------------------------
    # SLO / error budget
    # ------------------------------------------------------------------

    async def _loop_slo(self) -> None:
        async with get_db_context() as db:
            budgets = await compute_all_budgets(db, persist=True)
        for budget in budgets:
            if budget["status"] == BUDGET_EXHAUSTED:
                sre_events.slo_violation(budget["slo_id"], budget["service_id"], status=budget["status"], consumed=budget["consumed_percent"])
            if budget["burn_rate"] >= 1.0:
                sre_events.error_budget_burning(
                    budget["slo_id"],
                    budget["service_id"],
                    tier="slow" if budget["burn_rate"] < 6 else ("medium" if budget["burn_rate"] < 14.4 else "fast"),
                    burn_rate=budget["burn_rate"],
                )

    async def _loop_burn_rate(self) -> None:
        async with get_db_context() as db:
            result = await db.execute(select(SRESLO).where(SRESLO.status == "active"))
            slos = list(result.scalars().all())
            for slo in slos:
                status = await slo_service.burn_rate_status(db, slo)
                if status["burning"]:
                    burning_tiers = [tier for tier in BURN_TIERS if status["tiers"].get(tier, 0) >= status["thresholds"][tier]]
                    await create_alert(
                        db,
                        rule_name="burn-rate.burning",
                        severity="SEV2",
                        message=f"SLO {slo.slo_id} error budget burning ({', '.join(burning_tiers)} tier)",
                        service_id=slo.service_id,
                        metadata_json={"tiers": status["tiers"], "thresholds": status["thresholds"]},
                    )
                else:
                    await resolve_by_rule(db, "burn-rate.burning", service_id=slo.service_id)

    # ------------------------------------------------------------------
    # Dependency health
    # ------------------------------------------------------------------

    async def _loop_dependencies(self) -> None:
        from app.sre.dependencies import record_from_check_results
        from app.sre.health import health_checker

        results = await health_checker.run()
        async with get_db_context() as db:
            await record_from_check_results(db, results)
            down = [r.name for r in results if r.status == "down"]
            for dependency in down:
                sre_events.dependency_outage(dependency, kind="external", detail="health check failed")
            for result in results:
                set_dependency_status(result.name, result.status == "healthy")

    # ------------------------------------------------------------------
    # Certificates
    # ------------------------------------------------------------------

    async def _loop_certificates(self) -> None:
        from app.sre.certificates import cert_alert_message, check_certificates

        async with get_db_context() as db:
            changed = await check_certificates(db)
            if not changed:
                return
            for cert in changed:
                await create_alert(
                    db,
                    rule_name="tls.certificate",
                    severity="SEV3" if cert["status"] == CERT_EXPIRING else "SEV2",
                    message=cert_alert_message(cert),
                    service_id="platform",
                    metadata_json={"hostname": cert["hostname"], "status": cert["status"], "not_after": cert["not_after"]},
                )
                sre_events.certificate_expiring(cert["name"], cert["hostname"], status=cert["status"], not_after=cert["not_after"])

    # ------------------------------------------------------------------
    # Capacity warnings
    # ------------------------------------------------------------------

    async def _loop_capacity(self) -> None:
        from app.sre.capacity import saturation_summary

        async with get_db_context() as db:
            summary = await saturation_summary(db, days=1)
            for entry in summary:
                if entry["utilization_percent"] >= CAPACITY_ALERT_THRESHOLD_PERCENT:
                    await create_alert(
                        db,
                        rule_name="capacity.saturation",
                        severity="SEV2" if entry["saturation"] == "critical" else "SEV3",
                        message=f"capacity {entry['metric']} for {entry['service_id']} at {entry['utilization_percent']:.1f}%",
                        service_id=entry["service_id"],
                        region=entry.get("measured_at") or "",
                        metadata_json=entry,
                    )
                    sre_events.capacity_warning(entry["service_id"], entry["metric"], utilization=entry["utilization_percent"])
                else:
                    await resolve_by_rule(db, "capacity.saturation", service_id=entry["service_id"])

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    async def _loop_reports(self) -> None:
        from app.sre.reports import generate_daily_reports

        async with get_db_context() as db:
            await generate_daily_reports(db)


workers = SREWorkers()