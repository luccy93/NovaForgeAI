"""Volume 57 — LineageService (tenant-scoped, evidence-required, BFS traversal).

Provides:
  - record_edge with strict evidence + stage validation
  - trace_upstream / trace_downstream (BFS, depth-capped, tenant-scoped)
  - impact_analysis (downstream BFS summary)
  - set_ownership (explicit ownership stored on asset metadata)
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datagov.models import GovernanceDataAsset, GovernanceLineage

logger = logging.getLogger(__name__)

VALID_STAGES: set[str] = {
    "discover",
    "store",
    "retrieve",
    "model",
    "output",
    "export",
    "transform",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    """Best-effort audit; never raises."""
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        try:
            audit_service.log(
                tenant,
                actor,
                "user",
                action,
                "governance_lineage",
                resource_id,
                "success",
                details or {},
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "governance_lineage", resource_id, "success", details or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


class LineageService:
    """Tenant-scoped data-lineage service."""

    # ── record ──────────────────────────────────────────────────────────

    async def record_edge(
        self,
        db: AsyncSession,
        tenant: str,
        source_asset: str,
        target_asset: str,
        transformation: str,
        evidence: str,
        stage: str,
        metadata: dict | None = None,
    ) -> GovernanceLineage:
        """Create a GovernanceLineage row.

        Requires non-empty evidence (never fabricate lineage) and a valid stage.
        """
        if not tenant or not source_asset or not target_asset:
            raise ValueError("tenant, source_asset and target_asset are required")
        if not transformation or not str(transformation).strip():
            raise ValueError("transformation is required")
        # evidence required — never fabricate lineage
        if evidence is None or (isinstance(evidence, str) and not evidence.strip()):
            raise ValueError("evidence required — never fabricate lineage")
        if isinstance(evidence, str) and not evidence.strip():
            raise ValueError("evidence required — never fabricate lineage")
        if not evidence:
            raise ValueError("evidence required — never fabricate lineage")

        stage_norm = str(stage).strip().lower() if stage else ""
        if stage_norm not in VALID_STAGES:
            raise ValueError(f"invalid stage '{stage}'; allowed: {sorted(VALID_STAGES)}")

        # ensure evidence is stored as string
        evidence_str = str(evidence).strip()

        metadata_json = dict(metadata) if isinstance(metadata, dict) else {}

        row = GovernanceLineage(
            tenant=tenant,
            source_asset=source_asset,
            target_asset=target_asset,
            transformation=str(transformation).strip(),
            evidence=evidence_str,
            stage=stage_norm,
            metadata_json=metadata_json,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)

        _audit(
            tenant,
            "system",
            "governance.lineage.recorded",
            str(row.id),
            {
                "source_asset": source_asset,
                "target_asset": target_asset,
                "transformation": transformation,
                "stage": stage_norm,
            },
        )
        return row

    # ── trace upstream ────────────────────────────────────────────────

    async def trace_upstream(
        self,
        db: AsyncSession,
        tenant: str,
        asset_id: str,
        depth: int = 10,
    ) -> list[GovernanceLineage]:
        """BFS upstream traversal (target -> source) with depth cap.

        Returns list of GovernanceLineage edges reachable upstream from asset_id,
        tenant-scoped, breadth-first, depth-limited. Caps depth to avoid
        unbounded graph expansion.
        """
        if not tenant or not asset_id:
            raise ValueError("tenant and asset_id are required")
        if depth < 1:
            return []
        depth = min(int(depth), 50)  # hard cap

        visited: set[str] = set()
        # queue holds (current_asset_id, current_depth)
        queue: deque[tuple[str, int]] = deque()
        queue.append((asset_id, 0))
        visited.add(asset_id)

        edges: list[GovernanceLineage] = []
        seen_edge_ids: set[str] = set()

        while queue:
            current, cur_depth = queue.popleft()
            if cur_depth >= depth:
                continue
            stmt = select(GovernanceLineage).where(
                GovernanceLineage.tenant == tenant,
                GovernanceLineage.target_asset == current,
            )
            result = await db.execute(stmt)
            rows = list(result.scalars().all())
            for edge in rows:
                eid = str(edge.id)
                if eid in seen_edge_ids:
                    continue
                seen_edge_ids.add(eid)
                edges.append(edge)
                src = edge.source_asset
                if src not in visited:
                    visited.add(src)
                    queue.append((src, cur_depth + 1))

        return edges

    # ── trace downstream ──────────────────────────────────────────────

    async def trace_downstream(
        self,
        db: AsyncSession,
        tenant: str,
        asset_id: str,
        depth: int = 10,
    ) -> list[GovernanceLineage]:
        """BFS downstream traversal (source -> target) with depth cap."""
        if not tenant or not asset_id:
            raise ValueError("tenant and asset_id are required")
        if depth < 1:
            return []
        depth = min(int(depth), 50)

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque()
        queue.append((asset_id, 0))
        visited.add(asset_id)

        edges: list[GovernanceLineage] = []
        seen_edge_ids: set[str] = set()

        while queue:
            current, cur_depth = queue.popleft()
            if cur_depth >= depth:
                continue
            stmt = select(GovernanceLineage).where(
                GovernanceLineage.tenant == tenant,
                GovernanceLineage.source_asset == current,
            )
            result = await db.execute(stmt)
            rows = list(result.scalars().all())
            for edge in rows:
                eid = str(edge.id)
                if eid in seen_edge_ids:
                    continue
                seen_edge_ids.add(eid)
                edges.append(edge)
                tgt = edge.target_asset
                if tgt not in visited:
                    visited.add(tgt)
                    queue.append((tgt, cur_depth + 1))

        return edges

    # ── impact analysis ───────────────────────────────────────────────

    async def impact_analysis(
        self,
        db: AsyncSession,
        tenant: str,
        asset_id: str,
        depth: int = 10,
    ) -> dict[str, Any]:
        """Downstream impact analysis for a given asset.

        BFS downstream from asset_id, returns summary including all downstream
        edges, impacted asset ids, and counts. Depth-capped.
        """
        edges = await self.trace_downstream(db, tenant, asset_id, depth=depth)

        impacted_assets: list[str] = []
        seen: set[str] = set()
        for e in edges:
            if e.target_asset not in seen:
                seen.add(e.target_asset)
                impacted_assets.append(e.target_asset)
            if e.source_asset not in seen and e.source_asset != asset_id:
                seen.add(e.source_asset)
                impacted_assets.append(e.source_asset)

        # ensure deterministic ordering while preserving BFS discovery order
        return {
            "asset_id": asset_id,
            "tenant": tenant,
            "depth": depth,
            "impact_count": len(impacted_assets),
            "impacted_assets": impacted_assets,
            "edges": edges,
            "edge_count": len(edges),
        }

    # ── ownership ─────────────────────────────────────────────────────

    async def set_ownership(
        self,
        db: AsyncSession,
        tenant: str,
        asset_id: str,
        owner: str | None = None,
        steward: str | None = None,
        custodian: str | None = None,
        processor: str | None = None,
    ) -> GovernanceDataAsset:
        """Set explicit ownership assignments; stored on asset metadata.

        Updates GovernanceDataAsset.owner column when `owner` is provided and
        always stores steward/custodian/processor (and owner mirror) inside
        metadata_json.ownership for explicit, auditable assignments.
        """
        if not tenant or not asset_id:
            raise ValueError("tenant and asset_id are required")
        # at least one assignment must be provided
        if all(v is None for v in (owner, steward, custodian, processor)):
            raise ValueError("at least one of owner, steward, custodian, processor is required")

        stmt = select(GovernanceDataAsset).where(
            GovernanceDataAsset.tenant == tenant,
            GovernanceDataAsset.asset_id == asset_id,
        )
        result = await db.execute(stmt)
        asset: GovernanceDataAsset | None = result.scalars().first()
        if asset is None:
            raise ValueError(f"asset '{asset_id}' not found for tenant '{tenant}'")

        meta: dict = dict(asset.metadata_json or {})
        ownership: dict = dict(meta.get("ownership", {}))

        # owner is both column and ownership map
        if owner is not None:
            owner_str = str(owner).strip()
            if not owner_str:
                raise ValueError("owner cannot be empty")
            asset.owner = owner_str
            ownership["owner"] = owner_str
            meta["owner"] = owner_str  # keep flat alias for compatibility

        if steward is not None:
            steward_str = str(steward).strip()
            if not steward_str:
                raise ValueError("steward cannot be empty")
            ownership["steward"] = steward_str
            meta["steward"] = steward_str

        if custodian is not None:
            custodian_str = str(custodian).strip()
            if not custodian_str:
                raise ValueError("custodian cannot be empty")
            ownership["custodian"] = custodian_str
            meta["custodian"] = custodian_str

        if processor is not None:
            processor_str = str(processor).strip()
            if not processor_str:
                raise ValueError("processor cannot be empty")
            ownership["processor"] = processor_str
            meta["processor"] = processor_str

        ownership["updated_at"] = _utc_now().isoformat()
        # tenant scoping marker
        ownership["tenant"] = tenant
        meta["ownership"] = ownership
        asset.metadata_json = meta

        await db.flush()
        await db.refresh(asset)

        _audit(
            tenant,
            owner or steward or custodian or processor or "system",
            "governance.ownership.updated",
            asset_id,
            {"ownership": ownership},
        )
        return asset


lineage_service = LineageService()
