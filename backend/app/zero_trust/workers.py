"""Zero Trust workers — risk, anomaly, expiration, campaigns, posture, orphans."""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_context

logger = logging.getLogger(__name__)


async def risk_calculation_worker(db: AsyncSession | None = None):
    # Re-evaluate risk for active sessions
    try:
        async with get_db_context() as db:
            from sqlalchemy import select
            from app.iam.models import IAMSession
            q = select(IAMSession).where(IAMSession.is_active == True).limit(100)  # noqa: E712
            res = await db.execute(q)
            sessions = res.scalars().all()
            for sess in sessions:
                tenant = str(sess.tenant_id or sess.organization_id or "")
                identity = sess.identity_id or str(sess.user_id)
                try:
                    from app.zero_trust.continuous import calculate_access_risk
                    await calculate_access_risk(db, tenant, identity, {"session": str(sess.id)})
                except Exception as e:
                    logger.debug("risk calc failed %s: %s", identity, e)
            await db.commit()
    except Exception as e:
        logger.debug("risk worker failed: %s", e)


async def anomaly_detection_worker(db: AsyncSession | None = None):
    try:
        async with get_db_context() as db:
            # Find distinct tenants from recent audit logs
            from app.iam.models import IAMAuditLog
            from sqlalchemy import select
            q = select(IAMAuditLog.organization_id).distinct().limit(10)
            res = await db.execute(q)
            tenants = [str(r[0]) for r in res.all() if r[0]]
            for tenant in tenants:
                try:
                    from app.zero_trust.anomaly import detect_anomalies
                    await detect_anomalies(db, tenant)
                except Exception as e:
                    logger.debug("anomaly %s: %s", tenant, e)
    except Exception as e:
        logger.debug("anomaly worker outer: %s", e)


async def credential_expiration_worker(db: AsyncSession | None = None):
    try:
        async with get_db_context() as db:
            # Find tenants via credentials
            from app.zero_trust.models import IAMCredentialsMetadata
            from sqlalchemy import select
            q = select(IAMCredentialsMetadata.tenant_id).distinct().limit(20)
            res = await db.execute(q)
            tenants = [str(r[0]) for r in res.all() if r[0]]
            for tenant in tenants:
                try:
                    from app.zero_trust.credentials import check_expiring
                    expiring = await check_expiring(db, tenant, warning_days=7)
                    for item in expiring:
                        logger.info("credential expiring %s %s", tenant, item)
                except Exception as e:
                    logger.debug("cred exp %s: %s", tenant, e)
            await db.commit()
    except Exception as e:
        logger.debug("cred expiration worker: %s", e)


async def review_campaign_worker(db: AsyncSession | None = None):
    try:
        from app.iam.access_review_service import access_review_service
        # Auto-create periodic campaigns if enabled and overdue
        # For each org with pending reviews overdue, escalate
        # Simplified: just log
        logger.debug("review campaign tick")
    except Exception as e:
        logger.debug("review campaign: %s", e)


async def posture_analysis_worker(db: AsyncSession | None = None):
    try:
        async with get_db_context() as db:
            from app.zero_trust.posture import get_identity_posture
            from sqlalchemy import select
            from app.iam.models import IAMAuditLog
            q = select(IAMAuditLog.organization_id).distinct().limit(5)
            res = await db.execute(q)
            tenants = [str(r[0]) for r in res.all() if r[0]]
            for tenant in tenants:
                try:
                    await get_identity_posture(db, tenant)
                except Exception as e:
                    logger.debug("posture %s: %s", tenant, e)
    except Exception as e:
        logger.debug("posture worker: %s", e)


async def orphan_detection_worker(db: AsyncSession | None = None):
    try:
        async with get_db_context() as db:
            from app.zero_trust.posture import _count_orphaned
            from sqlalchemy import select
            from app.zero_trust.models import IAMCredentialsMetadata
            q = select(IAMCredentialsMetadata.tenant_id).distinct().limit(10)
            res = await db.execute(q)
            tenants = [str(r[0]) for r in res.all() if r[0]]
            for tenant in tenants:
                try:
                    cnt = await _count_orphaned(db, tenant)
                    if cnt:
                        logger.info("orphaned %s count %s", tenant, cnt)
                except Exception as e:
                    logger.debug("orphan %s: %s", tenant, e)
    except Exception as e:
        logger.debug("orphan worker: %s", e)


async def run_all_workers():
    await risk_calculation_worker()
    await anomaly_detection_worker()
    await credential_expiration_worker()
    await posture_analysis_worker()
    await orphan_detection_worker()
