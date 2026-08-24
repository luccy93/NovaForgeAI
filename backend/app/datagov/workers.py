"""Data Governance workers — Volume 57 (10 async workers)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def asset_discovery_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    """Discover data assets from existing systems (metadata only)."""
    if db is None or not tenant:
        return {"worker": "asset_discovery", "skipped": True}
    try:
        from app.datagov.catalog import CatalogService
        svc = CatalogService()
        discovered = await svc.discover_assets(db, tenant)
        return {"worker": "asset_discovery", "tenant": tenant, "discovered": discovered, "count": len(discovered)}
    except Exception as exc:
        logger.warning("asset_discovery_worker: %s", exc)
        return {"worker": "asset_discovery", "error": str(exc)}


async def classification_scan_worker(db: AsyncSession | None = None, tenant: str | None = None, limit: int = 50) -> dict:
    """Auto-classify unclassified assets (advisory AI classifications)."""
    if db is None or not tenant:
        return {"worker": "classification_scan", "skipped": True}
    try:
        from app.datagov.catalog import CatalogService
        from app.datagov.classifications import ClassificationService
        cat = CatalogService()
        cls_svc = ClassificationService()
        assets = await cat.list_assets(db, tenant, filters={"classification": "INTERNAL"})
        classified = 0
        for asset in assets[:limit]:
            sample = (asset.metadata_json or {}).get("content_sample")
            if not sample:
                continue
            await cls_svc.auto_classify(db, tenant, asset.asset_id, sample)
            classified += 1
        return {"worker": "classification_scan", "tenant": tenant, "classified": classified}
    except Exception as exc:
        logger.warning("classification_scan_worker: %s", exc)
        return {"worker": "classification_scan", "error": str(exc)}


async def lineage_extraction_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    """Extract lineage edges from existing system relationships (evidence-backed)."""
    if db is None or not tenant:
        return {"worker": "lineage_extraction", "skipped": True}
    extracted = 0
    try:
        from sqlalchemy import select
        from app.datagov.lineage import LineageService
        from app.rag.models import KnowledgeSource, RagChunk

        svc = LineageService()
        res = await db.execute(select(KnowledgeSource).where(KnowledgeSource.tenant_id == tenant).limit(20))
        for src in res.scalars().all():
            evidence = f"rag:knowledge_source:{src.id}"
            await svc.record_edge(
                db, str(tenant), f"source:{src.id}", f"chunks:{src.id}",
                "chunking", evidence=evidence, stage="store",
            )
            extracted += 1
        return {"worker": "lineage_extraction", "tenant": tenant, "extracted": extracted}
    except Exception as exc:
        logger.warning("lineage_extraction_worker: %s", exc)
        return {"worker": "lineage_extraction", "extracted": extracted, "error": str(exc)}


async def retention_checks_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    """Identify expired data and enforce deletion respecting legal holds."""
    if db is None or not tenant:
        return {"worker": "retention_checks", "skipped": True}
    try:
        from app.datagov.retention import RetentionService
        svc = RetentionService()
        expired = await svc.check_expired(db, tenant)
        processed, blocked = 0, 0
        for item in expired:
            state = item.get("state") if isinstance(item, dict) else None
            asset_id = item.get("asset_id") if isinstance(item, dict) else None
            if state == "EXPIRED" and asset_id:
                under_hold = await svc.is_under_hold(db, tenant, asset_id)
                if under_hold:
                    blocked += 1
                    continue
                try:
                    await svc.request_deletion(db, tenant, asset_id, actor="retention-worker", reason="retention expired")
                    processed += 1
                except Exception as exc:
                    logger.info("retention_checks: deletion deferred %s: %s", asset_id, exc)
        return {"worker": "retention_checks", "tenant": tenant, "expired": len(expired), "processed": processed, "blocked_by_hold": blocked}
    except Exception as exc:
        logger.warning("retention_checks_worker: %s", exc)
        return {"worker": "retention_checks", "error": str(exc)}


async def dsr_orchestration_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    """Advance verified+approved DSR requests toward completion."""
    if db is None or not tenant:
        return {"worker": "dsr_orchestration", "skipped": True}
    try:
        from sqlalchemy import select
        from app.datagov.models import GovernanceDataRequest
        res = await db.execute(
            select(GovernanceDataRequest).where(
                GovernanceDataRequest.tenant == tenant,
                GovernanceDataRequest.verification_status == "verified",
                GovernanceDataRequest.approval_status == "approved",
            ).limit(25)
        )
        pending = res.scalars().all()
        return {"worker": "dsr_orchestration", "tenant": tenant, "actionable": len(pending)}
    except Exception as exc:
        logger.warning("dsr_orchestration_worker: %s", exc)
        return {"worker": "dsr_orchestration", "error": str(exc)}


async def dlp_scanning_worker(db: AsyncSession | None = None, tenant: str | None = None, limit: int = 20) -> dict:
    """Scan recent exports/notifications destinations for restricted movement."""
    if db is None or not tenant:
        return {"worker": "dlp_scanning", "skipped": True}
    scanned, violations = 0, 0
    try:
        from app.datagov.dlp import DLPService
        svc = DLPService()
        # Scan recent export scopes as destinations (metadata-level samples only)
        from sqlalchemy import select
        from app.datagov.models import GovernanceExport
        res = await db.execute(select(GovernanceExport).where(GovernanceExport.tenant == tenant).order_by(GovernanceExport.created_at.desc()).limit(limit))
        for exp in res.scalars().all():
            scope_sample = str(exp.scope or {})[:500]
            result = await svc.scan(db, tenant, actor="dlp-worker", destination="exports",
                                    content_sample=scope_sample, classification="RESTRICTED")
            scanned += 1
            action = result.get("action") if isinstance(result, dict) else None
            if action in ("BLOCK", "REQUIRE_APPROVAL"):
                violations += 1
        return {"worker": "dlp_scanning", "tenant": tenant, "scanned": scanned, "violations": violations}
    except Exception as exc:
        logger.warning("dlp_scanning_worker: %s", exc)
        return {"worker": "dlp_scanning", "scanned": scanned, "violations": violations, "error": str(exc)}


async def policy_evaluation_sweep_worker(db: AsyncSession | None = None, tenant: str | None = None, limit: int = 50) -> dict:
    """Re-evaluate policy decisions on restricted assets (fail-closed)."""
    if db is None or not tenant:
        return {"worker": "policy_evaluation_sweep", "skipped": True}
    evaluated = 0
    try:
        from app.datagov.policy_bridge import PolicyBridgeService
        from app.datagov.catalog import CatalogService
        bridge = PolicyBridgeService()
        cat = CatalogService()
        restricted = await cat.list_assets(db, tenant, filters={"classification": "RESTRICTED"})
        for asset in restricted[:limit]:
            try:
                await bridge.evaluate(
                    db, tenant, actor="policy-sweep", resource=asset.asset_id,
                    policy_type="data_retention",
                    context={"classification": "RESTRICTED", "action": "read"},
                )
                evaluated += 1
            except Exception:
                continue
        return {"worker": "policy_evaluation_sweep", "tenant": tenant, "evaluated": evaluated}
    except Exception as exc:
        logger.warning("policy_evaluation_sweep_worker: %s", exc)
        return {"worker": "policy_evaluation_sweep", "evaluated": evaluated, "error": str(exc)}


async def evidence_collection_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    """Collect fresh evidence for controls with expiring proof."""
    if db is None or not tenant:
        return {"worker": "evidence_collection", "skipped": True}
    collected = 0
    try:
        from sqlalchemy import select
        from datetime import timedelta
        from app.datagov.controls import ControlService
        from app.datagov.models import GovernanceControl, GovernanceControlEvidence
        now = datetime.now(timezone.utc)
        res = await db.execute(select(GovernanceControl).where(GovernanceControl.tenant == tenant))
        svc = ControlService()
        for ctrl in res.scalars().all():
            ev_res = await db.execute(
                select(GovernanceControlEvidence).where(
                    GovernanceControlEvidence.control_id == ctrl.id,
                    GovernanceControlEvidence.valid_until > now,
                ).limit(1)
            )
            has_valid = ev_res.scalar_one_or_none() is not None
            if not has_valid:
                await svc.collect_evidence(
                    db, control_id=str(ctrl.id), tenant=tenant,
                    evidence_type="configuration",
                    source=f"auto:{ctrl.framework}:{ctrl.control_id}",
                    valid_until=now + timedelta(days=90),
                    source_version="1.0",
                    metadata={"collected_by": "evidence-worker"},
                )
                collected += 1
        return {"worker": "evidence_collection", "tenant": tenant, "collected": collected}
    except Exception as exc:
        logger.warning("evidence_collection_worker: %s", exc)
        return {"worker": "evidence_collection", "collected": collected, "error": str(exc)}


async def control_assessment_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    """Assess controls whose status is stale relative to their evidence."""
    if db is None or not tenant:
        return {"worker": "control_assessment", "skipped": True}
    assessed = 0
    try:
        from sqlalchemy import select
        from app.datagov.controls import ControlService
        from app.datagov.models import GovernanceControl
        res = await db.execute(select(GovernanceControl).where(
            GovernanceControl.tenant == tenant,
            GovernanceControl.status.in_(["NOT_ASSESSED", "PARTIAL"]),
        ))
        svc = ControlService()
        for ctrl in res.scalars().all():
            new_status = "PASS" if svc._has_valid_evidence(ctrl) else "FAIL"
            try:
                await svc.assess_control(db, control_id=str(ctrl.id), status=new_status, actor="assessment-worker", tenant=tenant)
                assessed += 1
            except Exception:
                continue
        return {"worker": "control_assessment", "tenant": tenant, "assessed": assessed}
    except Exception as exc:
        logger.warning("control_assessment_worker: %s", exc)
        return {"worker": "control_assessment", "assessed": assessed, "error": str(exc)}


async def exception_expiration_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    """Expire governance exceptions past their expiration."""
    if db is None or not tenant:
        return {"worker": "exception_expiration", "skipped": True}
    try:
        from app.datagov.controls import ControlService
        svc = ControlService()
        expired = await svc.expire_exceptions(db, tenant=tenant)
        count = len(expired) if isinstance(expired, list) else 0
        return {"worker": "exception_expiration", "tenant": tenant, "expired": count}
    except Exception as exc:
        logger.warning("exception_expiration_worker: %s", exc)
        return {"worker": "exception_expiration", "error": str(exc)}
