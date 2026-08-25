"""Volume 59 Commit 2 — AIOps workers (7)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def anomaly_detection_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "anomaly_detection", "skipped": True}
    try:
        from app.observability.aiops import aiops_engine
        res = await aiops_engine.detect_anomalies(db, tenant, metric="latency", window_hours=1)
        return {"worker": "anomaly_detection", "tenant": tenant, "anomalies": res.get("anomalies", []) if isinstance(res, dict) else 0}
    except Exception as e:
        logger.warning("anomaly_detection_worker: %s", e)
        return {"worker": "anomaly_detection", "error": str(e)}


async def alert_correlation_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "alert_correlation", "skipped": True}
    try:
        from app.observability.platform import platform_service
        from sqlalchemy import select
        from app.observability.models import ObservabilityAlert
        res = await db.execute(select(ObservabilityAlert).where(ObservabilityAlert.tenant == tenant, ObservabilityAlert.status == "FIRING").limit(10))
        alerts = list(res.scalars().all())
        correlated = 0
        for a in alerts:
            try:
                await platform_service.correlate_alerts(db, tenant, str(a.id))
                correlated += 1
            except Exception:
                continue
        return {"worker": "alert_correlation", "tenant": tenant, "correlated": correlated}
    except Exception as e:
        logger.warning("alert_correlation_worker: %s", e)
        return {"worker": "alert_correlation", "error": str(e)}


async def root_cause_analysis_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "root_cause_analysis", "skipped": True}
    try:
        from app.observability.aiops import aiops_engine
        from sqlalchemy import select
        from app.sre.models import SREIncident
        res = await db.execute(select(SREIncident).where(SREIncident.tenant == tenant).order_by(SREIncident.created_at.desc()).limit(5))
        incidents = list(res.scalars().all())
        analyzed = 0
        for inc in incidents:
            try:
                await aiops_engine.assist_root_cause(db, tenant, str(inc.id))
                analyzed += 1
            except Exception:
                continue
        return {"worker": "root_cause_analysis", "tenant": tenant, "analyzed": analyzed}
    except Exception as e:
        logger.warning("root_cause_analysis_worker: %s", e)
        return {"worker": "root_cause_analysis", "error": str(e)}


async def forecasting_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "forecasting", "skipped": True}
    try:
        from app.observability.remediation import remediation_service
        res = await remediation_service.forecast_capacity(db, tenant)
        return {"worker": "forecasting", "tenant": tenant, "forecast": res}
    except Exception as e:
        logger.warning("forecasting_worker: %s", e)
        return {"worker": "forecasting", "error": str(e)}


async def cost_anomaly_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "cost_anomaly", "skipped": True}
    try:
        from app.observability.remediation import remediation_service
        res = await remediation_service.detect_cost_anomalies(db, tenant)
        return {"worker": "cost_anomaly", "tenant": tenant, "anomalies": res}
    except Exception as e:
        logger.warning("cost_anomaly_worker: %s", e)
        return {"worker": "cost_anomaly", "error": str(e)}


async def observability_quality_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "observability_quality", "skipped": True}
    try:
        from app.observability.circuit_breaker import circuit_breaker_service
        res = await circuit_breaker_service.score_observability_quality(db, tenant)
        return {"worker": "observability_quality", "tenant": tenant, "score": res}
    except Exception as e:
        logger.warning("observability_quality_worker: %s", e)
        return {"worker": "observability_quality", "error": str(e)}


async def aiops_recommendation_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "aiops_recommendation", "skipped": True}
    try:
        from app.observability.aiops import aiops_engine
        # Generate recommendations for recent incidents
        from sqlalchemy import select
        from app.sre.models import SREIncident
        res = await db.execute(select(SREIncident).where(SREIncident.tenant == tenant).limit(5))
        incidents = list(res.scalars().all())
        generated = 0
        for inc in incidents:
            try:
                await aiops_engine.summarize_incident(db, tenant, str(inc.id))
                generated += 1
            except Exception:
                continue
        return {"worker": "aiops_recommendation", "tenant": tenant, "generated": generated}
    except Exception as e:
        logger.warning("aiops_recommendation_worker: %s", e)
        return {"worker": "aiops_recommendation", "error": str(e)}
