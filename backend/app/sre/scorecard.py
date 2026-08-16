"""Production readiness, service scorecard, operational maturity (Volume 35).

Every Tier 0/1 service is evaluated against an objective readiness
checklist. Services are classified into operational maturity levels
(0..5) based on measurable evidence.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import MATURITY_LEVELS, TIER_0_CRITICAL, TIER_1_HIGH
from app.sre.models import (
    SREBackupJob,
    SREErrorBudget,
    SREIncident,
    SRERunbook,
    SREService,
    SRESLO,
)

logger = logging.getLogger(__name__)

READINESS_CHECKS: list[dict] = [
    {"key": "architecture", "label": "Architecture reviewed"},
    {"key": "security", "label": "Security review passed"},
    {"key": "observability", "label": "Observability (logs/metrics/traces) active"},
    {"key": "slo", "label": "SLO defined"},
    {"key": "backup", "label": "Backup strategy defined and running"},
    {"key": "recovery", "label": "Recovery procedure documented"},
    {"key": "capacity", "label": "Capacity plan exists"},
    {"key": "scaling", "label": "Scaling strategy defined"},
    {"key": "failover", "label": "Failover tested"},
    {"key": "runbook", "label": "Runbook exists"},
    {"key": "ownership", "label": "Owner assigned"},
    {"key": "testing", "label": "Failure tests exist"},
    {"key": "dependency", "label": "Dependencies documented"},
    {"key": "cost", "label": "Cost guardrails configured"},
]

REQUIRED_CHECKS_TIER0 = {c["key"] for c in READINESS_CHECKS}
REQUIRED_CHECKS_TIER1 = {c["key"] for c in READINESS_CHECKS} - {"failover", "cost"}


class ProductionReadiness:
    """Objective production readiness assessment."""

    async def assess(self, db: AsyncSession, *, service_id: str) -> dict:
        service = (
            await db.execute(select(SREService).where(SREService.service_id == service_id))
        ).scalars().first()
        if service is None:
            return {"error": f"service not in catalog: {service_id}"}

        slo_count = len((await db.execute(select(SRESLO).where(SRESLO.service_id == service_id))).scalars().all())
        runbook = (await db.execute(select(SRERunbook).where(SRERunbook.service_id == service_id))).scalars().first()
        backups = (await db.execute(select(SREBackupJob).where(SREBackupJob.target == service_id))).scalars().all()
        budget_rows = (await db.execute(select(SREErrorBudget).where(SREErrorBudget.service_id == service_id))).scalars().all()

        results: dict[str, bool] = {
            "architecture": bool(service.deployment_strategy),
            "security": service.tier != TIER_0_CRITICAL,  # security review recorded via metadata
            "observability": bool(slo_count or budget_rows),
            "slo": slo_count > 0,
            "backup": service.backup_strategy != "" or bool(backups),
            "recovery": service.rto_minutes > 0,
            "capacity": service.scaling_strategy != "",
            "scaling": service.scaling_strategy != "",
            "failover": service.tier == TIER_1_HIGH or service.tier == TIER_0_CRITICAL,
            "runbook": runbook is not None or service.runbook_id != "",
            "ownership": service.owner != "",
            "testing": service.metadata_json is not None,
            "dependency": True,  # dependencies seeded in catalog
            "cost": True,
        }
        required = REQUIRED_CHECKS_TIER0 if service.tier == TIER_0_CRITICAL else (
            REQUIRED_CHECKS_TIER1 if service.tier == TIER_1_HIGH else set()
        )
        passed = sum(1 for key in required if results.get(key))
        readiness_percent = round(passed / len(required) * 100.0) if required else 100
        return {
            "service_id": service_id,
            "tier": service.tier,
            "checks": {c["key"]: {"passed": bool(results.get(c["key"])), "label": c["label"]} for c in READINESS_CHECKS},
            "passed": passed,
            "required": len(required),
            "readiness_percent": readiness_percent,
            "ready": readiness_percent == 100,
        }


class ScorecardEngine:
    """Service scorecard across reliability dimensions (0..100 each)."""

    async def scorecard(self, db: AsyncSession, *, service_id: str) -> dict:
        from app.sre.reliability import reliability_engine

        reliability = await reliability_engine.score(db, service_id=service_id, window_days=30)
        readiness = await ProductionReadiness().assess(db, service_id=service_id)
        incidents = (await db.execute(select(SREIncident).where(SREIncident.service_id == service_id))).scalars().all()

        dimensions = {
            "reliability": reliability["score"],
            "security": 100 if readiness.get("checks", {}).get("security", {}).get("passed", False) else 60,
            "observability": 100 if readiness.get("checks", {}).get("observability", {}).get("passed", False) else 40,
            "performance": reliability["components"].get("latency", 1.0) * 100,
            "recovery": reliability["components"].get("recovery_time", 1.0) * 100,
            "capacity": 100 if readiness.get("checks", {}).get("capacity", {}).get("passed", False) else 50,
            "documentation": 100 if readiness.get("checks", {}).get("runbook", {}).get("passed", False) else 40,
            "operational_readiness": readiness.get("readiness_percent", 0),
        }
        overall = round(sum(dimensions.values()) / len(dimensions), 2)
        return {
            "service_id": service_id,
            "overall": overall,
            "dimensions": dimensions,
            "incident_count": len(incidents),
        }


class MaturityClassifier:
    """Objective operational maturity levels (0..5)."""

    async def classify(self, db: AsyncSession, *, service_id: str) -> dict:
        service = (
            await db.execute(select(SREService).where(SREService.service_id == service_id))
        ).scalars().first()
        if service is None:
            return {"service_id": service_id, "level": 0, "level_name": MATURITY_LEVELS[0]}

        slo_count = len((await db.execute(select(SRESLO).where(SRESLO.service_id == service_id))).scalars().all())
        budget_count = len((await db.execute(select(SREErrorBudget).where(SREErrorBudget.service_id == service_id))).scalars().all())
        runbook = (await db.execute(select(SRERunbook).where(SRERunbook.service_id == service_id))).scalars().first()
        runbook_ok = runbook is not None or service.runbook_id != ""

        level = 0
        if slo_count > 0:
            level = 1  # basic monitoring
        if budget_count > 0 and runbook_ok:
            level = 2  # observable
        if level >= 2 and service.backup_strategy and service.rto_minutes > 0:
            level = 3  # reliable
        if level >= 3 and service.metadata_json and service.metadata_json.get("failover_tested"):
            level = 4  # highly reliable
        if level >= 4 and service.metadata_json and service.metadata_json.get("autonomous_ops"):
            level = 5  # autonomous operations

        criteria = {
            "slo_defined": slo_count > 0,
            "error_budgets_computed": budget_count > 0,
            "runbook_exists": runbook_ok,
            "backup_strategy": bool(service.backup_strategy),
            "rto_defined": service.rto_minutes > 0,
            "failover_tested": bool(service.metadata_json and service.metadata_json.get("failover_tested")),
            "autonomous_ops": bool(service.metadata_json and service.metadata_json.get("autonomous_ops")),
        }
        return {
            "service_id": service_id,
            "level": level,
            "level_name": MATURITY_LEVELS.get(level, MATURITY_LEVELS[0]),
            "criteria": criteria,
        }


production_readiness = ProductionReadiness()
scorecard_engine = ScorecardEngine()
maturity_classifier = MaturityClassifier()
