"""Volume 57 — CatalogService (metadata-only, tenant-scoped).

Tenant-scoped asset registry backed by governance_data_assets.
discover_assets pulls counts/owner/location metadata from existing
subsystems (rag, KG, delivery, billing, support, analytics) without
copying content. Each source is wrapped in try/except so missing
tables never break discovery. Audit best-effort via app.iam.audit_service.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datagov.models import GovernanceDataAsset

logger = logging.getLogger(__name__)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    """Best-effort audit; never raises."""
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        # audit_service.log signature is flexible; try common variants
        try:
            audit_service.log(
                tenant,
                actor,
                "user",
                action,
                "governance_asset",
                resource_id,
                "success",
                details or {},
            )
        except TypeError:
            # fallback: (org_id, actor_id, actor_type, action, resource_type, resource_id, result, details)
            audit_service.log(tenant, actor, "user", action, "governance_asset", resource_id, "success", details or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CatalogService:
    """Tenant-scoped data-asset catalog."""

    # ── register ──────────────────────────────────────────────────────────

    async def register_asset(
        self,
        db: AsyncSession,
        tenant: str,
        asset_id: str,
        workspace: str | None = None,
        project: str | None = None,
        resource: str | None = None,
        type: str | None = None,  # noqa: A002  (spec requires param name `type`)
        owner: str | None = None,
        classification: str = "INTERNAL",
        source: str | None = None,
        location: str | None = None,
        retention_policy: str | None = None,
        sensitivity: str | None = None,
        metadata: dict | None = None,
    ) -> GovernanceDataAsset:
        """Create or update a GovernanceDataAsset (upsert on tenant+asset_id)."""
        if not tenant or not asset_id:
            raise ValueError("tenant and asset_id are required")
        if not resource or not type:
            raise ValueError("resource and type are required")

        asset_type = type  # preserve spec name
        metadata_json = dict(metadata) if metadata else {}

        # tenant+asset_id unique lookup
        stmt = select(GovernanceDataAsset).where(
            GovernanceDataAsset.tenant == tenant,
            GovernanceDataAsset.asset_id == asset_id,
        )
        result = await db.execute(stmt)
        existing: GovernanceDataAsset | None = result.scalars().first()

        if existing:
            existing.workspace = workspace
            existing.project = project
            existing.resource = resource
            setattr(existing, "type", asset_type)
            existing.owner = owner
            existing.classification = classification or existing.classification
            existing.source = source
            existing.location = location
            existing.retention_policy = retention_policy
            existing.sensitivity = sensitivity
            # merge metadata_json shallow
            if metadata_json:
                merged = dict(existing.metadata_json or {})
                merged.update(metadata_json)
                existing.metadata_json = merged
            await db.flush()
            await db.refresh(existing)
            _audit(tenant, owner or "system", "governance.asset.updated", asset_id, {"resource": resource, "type": asset_type})
            return existing

        row = GovernanceDataAsset(
            asset_id=asset_id,
            tenant=tenant,
            workspace=workspace,
            project=project,
            resource=resource,
            owner=owner,
            classification=classification or "INTERNAL",
            source=source,
            location=location,
            retention_policy=retention_policy,
            sensitivity=sensitivity,
            metadata_json=metadata_json,
        )
        # `type` is a model attribute named `type`; set via setattr to avoid shadowing
        setattr(row, "type", asset_type)
        db.add(row)
        await db.flush()
        await db.refresh(row)
        _audit(tenant, owner or "system", "governance.asset.registered", asset_id, {"resource": resource, "type": asset_type})
        return row

    # ── get ───────────────────────────────────────────────────────────────

    async def get_asset(
        self,
        db: AsyncSession,
        tenant: str,
        asset_id: str,
    ) -> GovernanceDataAsset | None:
        """Fetch single asset scoped to tenant."""
        stmt = select(GovernanceDataAsset).where(
            GovernanceDataAsset.tenant == tenant,
            GovernanceDataAsset.asset_id == asset_id,
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    # ── list ──────────────────────────────────────────────────────────────

    async def list_assets(
        self,
        db: AsyncSession,
        tenant: str,
        filters: dict | None = None,
    ) -> list[GovernanceDataAsset]:
        """List assets for tenant with optional equality filters.

        Supported filter keys: type, classification, owner, workspace,
        project, resource, sensitivity, source, location, retention_policy
        """
        filters = filters or {}
        stmt = select(GovernanceDataAsset).where(GovernanceDataAsset.tenant == tenant)

        # equality filters — only apply if column exists and value present
        for key in ("type", "classification", "owner", "workspace", "project", "resource", "sensitivity", "source", "location", "retention_policy"):
            val = filters.get(key)
            if val is None or val == "":
                continue
            col = getattr(GovernanceDataAsset, key, None)
            if col is not None:
                stmt = stmt.where(col == val)

        # optional metadata filter: metadata.owner etc not supported — ignore
        stmt = stmt.order_by(GovernanceDataAsset.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── discover ──────────────────────────────────────────────────────────

    async def discover_assets(
        self,
        db: AsyncSession,
        tenant: str,
    ) -> list[str]:
        """Discover assets from existing subsystems (metadata-only).

        For each known subsystem we attempt a COUNT(*) scoped to tenant
        where possible. Only metadata (counts, owner, location) is read;
        content is never copied. Each block is isolated with try/except
        so missing tables or schema differences do not abort discovery.

        Returns list of asset_ids that were discovered/ensured in the
        catalog.
        """
        discovered: list[str] = []

        async def _ensure(
            asset_id: str,
            asset_type: str,
            resource: str,
            owner: str | None,
            location: str | None,
            extra_meta: dict,
        ) -> None:
            """Idempotent upsert for discovered asset metadata."""
            try:
                stmt = select(GovernanceDataAsset).where(
                    GovernanceDataAsset.tenant == tenant,
                    GovernanceDataAsset.asset_id == asset_id,
                )
                res = await db.execute(stmt)
                existing = res.scalars().first()
                base_meta = {"discovered_at": _utc_now().isoformat(), "discovery": True}
                base_meta.update(extra_meta)
                if existing:
                    # merge counts without overwriting manual fields with None
                    merged = dict(existing.metadata_json or {})
                    merged.update(base_meta)
                    existing.metadata_json = merged
                    if owner and not existing.owner:
                        existing.owner = owner
                    if location and not existing.location:
                        existing.location = location
                    await db.flush()
                else:
                    row = GovernanceDataAsset(
                        asset_id=asset_id,
                        tenant=tenant,
                        workspace=None,
                        project=None,
                        resource=resource,
                        owner=owner,
                        classification="INTERNAL",
                        source="discovery",
                        location=location,
                        metadata_json=base_meta,
                    )
                    setattr(row, "type", asset_type)
                    db.add(row)
                    await db.flush()
                if asset_id not in discovered:
                    discovered.append(asset_id)
            except Exception as exc:  # noqa: BLE001
                logger.debug("discover _ensure %s failed: %s", asset_id, exc)

        # ── 1. RAG — KnowledgeSource / RagChunk ──────────────────────────
        try:
            from app.rag.models import KnowledgeSource, RagChunk  # type: ignore

            # KnowledgeSource counts
            try:
                stmt = select(func.count()).select_from(KnowledgeSource)
                # attempt tenant scoping — KnowledgeSource.tenant_id is UUID
                try:
                    tid = uuid.UUID(tenant)
                    stmt = stmt.where(KnowledgeSource.tenant_id == tid)
                except Exception:
                    # tenant is not UUID (e.g., "default") — skip scoping, count all but still record
                    pass
                result = await db.execute(stmt)
                cnt = int(result.scalar() or 0)
                # sample owner/location without copying content
                owner_val = None
                location_val = None
                try:
                    q = select(KnowledgeSource.owner_id, KnowledgeSource.source_uri).limit(1)
                    try:
                        tid2 = uuid.UUID(tenant)
                        q = q.where(KnowledgeSource.tenant_id == tid2)
                    except Exception:
                        pass
                    r = await db.execute(q)
                    row = r.first()
                    if row:
                        owner_val = str(row[0]) if row[0] else None
                        location_val = row[1]
                except Exception:
                    pass
                if cnt > 0 or True:  # always register discovery marker so caller sees asset
                    await _ensure(
                        asset_id=f"rag-sources-{tenant}",
                        asset_type="rag_source",
                        resource="rag_sources",
                        owner=owner_val,
                        location=location_val,
                        extra_meta={"source_table": "rag_sources", "count": cnt, "system": "rag"},
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("rag KnowledgeSource count failed: %s", exc)

            # RagChunk counts
            try:
                stmt2 = select(func.count()).select_from(RagChunk)
                try:
                    tid = uuid.UUID(tenant)
                    stmt2 = stmt2.where(RagChunk.tenant_id == tid)
                except Exception:
                    pass
                result2 = await db.execute(stmt2)
                cnt2 = int(result2.scalar() or 0)
                await _ensure(
                    asset_id=f"rag-chunks-{tenant}",
                    asset_type="rag_chunk",
                    resource="rag_chunks",
                    owner=None,
                    location=None,
                    extra_meta={"source_table": "rag_chunks", "count": cnt2, "system": "rag"},
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("rag RagChunk count failed: %s", exc)

        except Exception as exc:  # noqa: BLE001
            logger.debug("rag discovery skipped (models unavailable): %s", exc)

        # ── 2. Knowledge Graph — KGEntity ────────────────────────────────
        try:
            from app.knowledge_graph.models import KGEntity  # type: ignore

            try:
                stmt = select(func.count()).select_from(KGEntity).where(KGEntity.tenant == tenant)
                result = await db.execute(stmt)
                cnt = int(result.scalar() or 0)
                # sample owner/provider
                owner_val = None
                location_val = None
                try:
                    q = select(KGEntity.provider).where(KGEntity.tenant == tenant).limit(1)
                    r = await db.execute(q)
                    row = r.first()
                    if row:
                        owner_val = row[0]
                except Exception:
                    pass
                await _ensure(
                    asset_id=f"kg-entities-{tenant}",
                    asset_type="kg_entity",
                    resource="kg_entities",
                    owner=owner_val,
                    location=location_val,
                    extra_meta={"source_table": "kg_entities", "count": cnt, "system": "knowledge_graph"},
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("KGEntity count failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("knowledge_graph discovery skipped: %s", exc)

        # ── 3. Delivery artifacts ────────────────────────────────────────
        try:
            from app.delivery.models import DeliveryArtifact  # type: ignore

            try:
                stmt = select(func.count()).select_from(DeliveryArtifact).where(DeliveryArtifact.tenant == tenant)
                result = await db.execute(stmt)
                cnt = int(result.scalar() or 0)
                # sample location from storage_url
                loc = None
                try:
                    q = select(DeliveryArtifact.storage_url).where(DeliveryArtifact.tenant == tenant).limit(1)
                    r = await db.execute(q)
                    row = r.first()
                    if row:
                        loc = row[0]
                except Exception:
                    pass
                await _ensure(
                    asset_id=f"delivery-artifacts-{tenant}",
                    asset_type="delivery_artifact",
                    resource="delivery_artifacts",
                    owner=None,
                    location=loc,
                    extra_meta={"source_table": "delivery_artifacts", "count": cnt, "system": "delivery"},
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("DeliveryArtifact count failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("delivery discovery skipped: %s", exc)

        # ── 4. Billing records ───────────────────────────────────────────
        # Billing uses organization_id UUID; map tenant string if possible
        try:
            from app.billing.models import BillingInvoice, BillingSubscription, UsageMetering  # type: ignore

            for model, asset_suffix, rtype in [
                (BillingSubscription, "billing-subscriptions", "billing_subscriptions"),
                (BillingInvoice, "billing-invoices", "billing_invoices"),
                (UsageMetering, "billing-metering", "billing_usage_metering"),
            ]:
                try:
                    stmt = select(func.count()).select_from(model)
                    # attempt scoping via organization_id if tenant is UUID
                    try:
                        oid = uuid.UUID(tenant)
                        if hasattr(model, "organization_id"):
                            stmt = stmt.where(model.organization_id == oid)
                    except Exception:
                        # tenant is not UUID — count unscoped (still metadata-only)
                        pass
                    result = await db.execute(stmt)
                    cnt = int(result.scalar() or 0)
                    await _ensure(
                        asset_id=f"{asset_suffix}-{tenant}",
                        asset_type=rtype,
                        resource=rtype,
                        owner=None,
                        location=None,
                        extra_meta={"source_table": rtype, "count": cnt, "system": "billing"},
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("billing %s count failed: %s", rtype, exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("billing discovery skipped: %s", exc)

        # ── 5. Support tickets ───────────────────────────────────────────
        try:
            from app.support.models import SupportTicket  # type: ignore

            try:
                stmt = select(func.count()).select_from(SupportTicket).where(SupportTicket.tenant_id == tenant)
                result = await db.execute(stmt)
                cnt = int(result.scalar() or 0)
                # sample owner via assigned_agent
                owner_val = None
                try:
                    q = select(SupportTicket.assigned_agent).where(SupportTicket.tenant_id == tenant).limit(1)
                    r = await db.execute(q)
                    row = r.first()
                    if row:
                        owner_val = row[0]
                except Exception:
                    pass
                await _ensure(
                    asset_id=f"support-tickets-{tenant}",
                    asset_type="support_ticket",
                    resource="support_tickets",
                    owner=owner_val,
                    location=None,
                    extra_meta={"source_table": "support_tickets", "count": cnt, "system": "support"},
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("SupportTicket count failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("support discovery skipped: %s", exc)

        # ── 6. Analytics metrics ─────────────────────────────────────────
        # Analytics is often in-memory (lakehouse) plus optional DB tables.
        # We try several known metric/warehouse tables metadata-only.
        for attempt in [
            ("lakehouse_metrics", "analytics", "lakehouse_metrics"),
            ("governance_quality_metrics", "analytics", "governance_quality_metrics"),
        ]:
            table_name, asset_type, resource = attempt
            try:
                # generic count via raw SQL to avoid model dependency
                from sqlalchemy import text as _text

                result = await db.execute(_text(f"SELECT COUNT(*) FROM {table_name}"))  # noqa: S608
                cnt = int(result.scalar() or 0)
                await _ensure(
                    asset_id=f"{table_name}-{tenant}",
                    asset_type=asset_type,
                    resource=resource,
                    owner=None,
                    location=None,
                    extra_meta={"source_table": table_name, "count": cnt, "system": "analytics"},
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("analytics table %s skipped: %s", table_name, exc)

        # fallback: use MetricRegistry in-memory counts as metadata-only signal
        try:
            from app.lakehouse.metric_registry import MetricRegistry  # type: ignore

            try:
                reg = MetricRegistry()
                # seeded registry size indicates analytics capability
                cnt = len(getattr(reg, "metrics", {}))
                await _ensure(
                    asset_id=f"analytics-metrics-{tenant}",
                    asset_type="analytics_metric",
                    resource="analytics_metrics",
                    owner="platform",
                    location="lakehouse/metric_registry",
                    extra_meta={"source_table": "metric_registry", "count": cnt, "system": "analytics"},
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("analytics metric_registry count failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.debug("analytics discovery fallback skipped: %s", exc)

        # commit discovery markers if any were added
        try:
            await db.flush()
        except Exception as exc:  # noqa: BLE001
            logger.debug("discover flush skipped: %s", exc)

        _audit(tenant, "system", "governance.assets.discovered", "", {"discovered": discovered})
        return discovered


catalog_service = CatalogService()
