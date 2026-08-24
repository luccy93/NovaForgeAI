"""Volume 57 — ProcessorService (tenant-scoped vendor/processor registry + grants + residency).

Provides:
  - register_processor — creates GovernanceProcessor row (tenant-isolated)
  - list_processors    — tenant-scoped listing
  - get_processor      — tenant-scoped fetch by id
  - update_status      — transition status with validation + audit
  - revoke_access      — sets status revoked, appends audit trail, clears grants
  - check_cross_border — flags when source_region != processing_region
  - grant / revoke / list access grants — third-party data access tracking
    (stored in GovernanceProcessor.access_grants JSON)

All methods are AsyncSession, tenant-scoped, audit best-effort, no placeholders.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datagov.models import GovernanceProcessor

logger = logging.getLogger(__name__)

VALID_STATUSES: set[str] = {"active", "inactive", "suspended", "revoked", "pending", "approved", "rejected"}
# normalized set for comparison (lowercase)
NORMALIZED_VALID: set[str] = {s.lower() for s in VALID_STATUSES}

# region alias — conservative cross-border detection shares logic with ai_gate
_CROSS_BORDER_MARKERS: set[str] = {"external", "cross-border", "cross_border", "international", "unknown", "global"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        try:
            audit_service.log(
                tenant,
                actor,
                "user",
                action,
                "governance_processor",
                resource_id,
                "success",
                details or {},
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "governance_processor", resource_id, "success", details or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _norm_region(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _is_cross_border(source_region: str | None, processing_region: str | None) -> bool:
    """Flag when source_region != processing_region (case-insensitive, normalized).

    Also flags explicit external markers even if equal.
    """
    src = _norm_region(source_region)
    proc = _norm_region(processing_region)
    if not src and not proc:
        return False
    if not src or not proc:
        # one missing — cannot determine, treat as not flagged unless marker
        # but if proc is external marker, flag
        check = (proc or src or "").lower()
        if check in _CROSS_BORDER_MARKERS or "cross" in check:
            return True
        return False
    # normalize lower
    s_low = src.strip().lower()
    p_low = proc.strip().lower()
    if s_low == p_low:
        # equal but if both are external marker still flag? No, equal implies no transfer
        return False
    # explicit marker always flag
    if p_low in _CROSS_BORDER_MARKERS or "cross" in p_low or "external" in p_low:
        return True
    return s_low != p_low


class ProcessorService:
    """Tenant-scoped processor / vendor registry."""

    # ── register ────────────────────────────────────────────────────────

    async def register_processor(
        self,
        db: AsyncSession,
        tenant: str,
        provider: str,
        purpose: str,
        data_categories: list | None = None,
        region: str | None = None,
        contract_ref: str | None = None,
        status: str = "active",
    ) -> GovernanceProcessor:
        """Register a third-party processor.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant scope (required).
            provider: vendor/provider name (required, non-empty).
            purpose: purpose of processing (required, non-empty).
            data_categories: list of data categories (e.g., ["pii","financial"]).
            region: processing region (e.g., "us-east-1", "eu-west-1").
            contract_ref: DPA / contract reference.
            status: processor status (active/inactive/suspended/revoked/pending).

        Returns:
            Persisted GovernanceProcessor row.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()

        if not provider or not str(provider).strip():
            raise ValueError("provider is required and cannot be empty")
        provider_s = str(provider).strip()

        if not purpose or not str(purpose).strip():
            raise ValueError("purpose is required and cannot be empty")
        purpose_s = str(purpose).strip()

        # data_categories normalize to list
        if data_categories is None:
            cats: list = []
        elif isinstance(data_categories, list):
            cats = [str(c).strip() for c in data_categories if c is not None and str(c).strip()]
        elif isinstance(data_categories, str):
            cats = [str(data_categories).strip()] if str(data_categories).strip() else []
        else:
            cats = [str(data_categories).strip()]

        region_s = _norm_region(region)
        contract_s = str(contract_ref).strip() if contract_ref and str(contract_ref).strip() else None

        status_norm = str(status).strip().lower() if status and str(status).strip() else "active"
        if status_norm not in NORMALIZED_VALID:
            raise ValueError(f"invalid status '{status}'; allowed: {sorted(VALID_STATUSES)}")

        row = GovernanceProcessor(
            tenant=tenant_s,
            provider=provider_s,
            purpose=purpose_s,
            data_categories=cats,
            region=region_s,
            contract_ref=contract_s,
            status=status_norm,
            access_grants=[],
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)

        _audit(tenant_s, "system", "governance.processor.registered", str(row.id), {"provider": provider_s, "purpose": purpose_s, "region": region_s, "status": status_norm})
        return row

    # ── list ────────────────────────────────────────────────────────────

    async def list_processors(
        self,
        db: AsyncSession,
        tenant: str,
    ) -> list[GovernanceProcessor]:
        """List all processors for tenant (tenant-scoped)."""
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()
        stmt = select(GovernanceProcessor).where(GovernanceProcessor.tenant == tenant_s).order_by(GovernanceProcessor.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── get ─────────────────────────────────────────────────────────────

    async def get_processor(
        self,
        db: AsyncSession,
        tenant: str,
        processor_id: str,
    ) -> GovernanceProcessor | None:
        """Fetch single processor tenant-scoped by id.

        Args:
            tenant: tenant scope.
            processor_id: GovernanceProcessor id (uuid string).
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not processor_id or not str(processor_id).strip():
            raise ValueError("processor_id is required")
        tenant_s = str(tenant).strip()
        pid = _parse_uuid(str(processor_id).strip())
        if pid is not None:
            stmt = select(GovernanceProcessor).where(
                GovernanceProcessor.tenant == tenant_s,
                GovernanceProcessor.id == pid,
            )
        else:
            stmt = select(GovernanceProcessor).where(
                GovernanceProcessor.tenant == tenant_s,
                GovernanceProcessor.id == processor_id,  # type: ignore
            )
        result = await db.execute(stmt)
        return result.scalars().first()

    # ── update_status ───────────────────────────────────────────────────

    async def update_status(
        self,
        db: AsyncSession,
        tenant: str,
        processor_id: str,
        status: str,
        actor: str | None = None,
    ) -> GovernanceProcessor:
        """Update processor status (tenant-scoped).

        Args:
            tenant: tenant scope.
            processor_id: processor id.
            status: new status (active/inactive/suspended/revoked etc).
            actor: actor performing change (for audit).

        Returns:
            Updated row.
        """
        if not tenant or not processor_id or not status:
            raise ValueError("tenant, processor_id and status are required")
        status_norm = str(status).strip().lower()
        if status_norm not in NORMALIZED_VALID:
            raise ValueError(f"invalid status '{status}'; allowed: {sorted(VALID_STATUSES)}")

        row = await self.get_processor(db, tenant, processor_id)
        if row is None:
            raise ValueError(f"processor '{processor_id}' not found for tenant '{tenant}'")

        old_status = row.status
        row.status = status_norm
        # append status change to access_grants audit trail (reuse field) or metadata?
        # Use access_grants as append-only audit for status changes when no grants table
        try:
            grants = list(row.access_grants or [])
            grants.append(
                {
                    "action": "status_change",
                    "from": old_status,
                    "to": status_norm,
                    "by": str(actor).strip() if actor and str(actor).strip() else "system",
                    "at": _utc_now().isoformat(),
                }
            )
            row.access_grants = grants
        except Exception:
            pass

        await db.flush()
        await db.refresh(row)

        _audit(str(tenant).strip(), str(actor).strip() if actor and str(actor).strip() else "system", "governance.processor.status_updated", str(row.id), {"from": old_status, "to": status_norm})
        return row

    # ── revoke_access ───────────────────────────────────────────────────

    async def revoke_access(
        self,
        db: AsyncSession,
        tenant: str,
        processor_id: str,
        actor: str | None = None,
        reason: str | None = None,
    ) -> GovernanceProcessor:
        """Revoke processor access — sets status revoked, adds audit entry, revokes grants.

        Args:
            tenant: tenant scope.
            processor_id: processor id.
            actor: actor performing revocation.
            reason: optional reason.

        Returns:
            Updated row with status revoked.
        """
        if not tenant or not processor_id:
            raise ValueError("tenant and processor_id are required")
        row = await self.get_processor(db, tenant, processor_id)
        if row is None:
            raise ValueError(f"processor '{processor_id}' not found for tenant '{tenant}'")

        old_status = row.status
        row.status = "revoked"

        # add audit entry to access_grants trail and mark all grants revoked
        try:
            grants = list(row.access_grants or [])
            # mark existing grant entries as revoked where not already
            for g in grants:
                if isinstance(g, dict) and "action" not in g:
                    # this is a grant entry
                    if g.get("revoked_at") is None and g.get("status") != "revoked":
                        g["status"] = "revoked"
                        g["revoked_at"] = _utc_now().isoformat()
                        g["revoked_by"] = str(actor).strip() if actor and str(actor).strip() else "system"
                        g["revoke_reason"] = str(reason).strip() if reason and str(reason).strip() else "processor revoked"
            grants.append(
                {
                    "action": "revoke_access",
                    "from": old_status,
                    "to": "revoked",
                    "by": str(actor).strip() if actor and str(actor).strip() else "system",
                    "at": _utc_now().isoformat(),
                    "reason": str(reason).strip() if reason and str(reason).strip() else None,
                }
            )
            row.access_grants = grants
        except Exception:
            pass

        await db.flush()
        await db.refresh(row)

        _audit(str(tenant).strip(), str(actor).strip() if actor and str(actor).strip() else "system", "governance.processor.revoked", str(row.id), {"from": old_status, "reason": reason, "provider": row.provider})
        return row

    # ── check_cross_border ──────────────────────────────────────────────

    async def check_cross_border(
        self,
        db: AsyncSession,
        tenant: str,
        source_region: str | None = None,
        processing_region: str | None = None,
        processor_id: str | None = None,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        """Check cross-border data transfer residency.

        Flags when source_region != processing_region. If processor_id is
        provided, its region is used as processing_region when not explicitly
        passed. If asset_id is provided, asset metadata region is used as
        source_region when not explicitly passed.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant scope.
            source_region: source/origin region (explicit, optional).
            processing_region: processor/target region (explicit, optional).
            processor_id: optional GovernanceProcessor id to infer processing_region.
            asset_id: optional GovernanceDataAsset asset_id to infer source_region.

        Returns:
            dict with cross_border (bool), source_region, processing_region,
            requires_approval (bool), reason, processor_id, asset_id.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()

        # infer processing_region from processor if needed
        proc_region = _norm_region(processing_region)
        src_region = _norm_region(source_region)

        processor: GovernanceProcessor | None = None
        if processor_id and str(processor_id).strip() and proc_region is None:
            try:
                processor = await self.get_processor(db, tenant_s, str(processor_id).strip())
                if processor is not None and processor.region:
                    proc_region = _norm_region(processor.region)
            except Exception as exc:  # noqa: BLE001
                logger.debug("check_cross_border processor lookup failed: %s", exc)

        # infer source_region from asset if needed
        if asset_id and str(asset_id).strip() and src_region is None:
            try:
                from app.datagov.models import GovernanceDataAsset

                stmt = select(GovernanceDataAsset).where(
                    GovernanceDataAsset.tenant == tenant_s,
                    GovernanceDataAsset.asset_id == str(asset_id).strip(),
                )
                result = await db.execute(stmt)
                asset = result.scalars().first()
                if asset is not None:
                    # try location, then metadata_json region, then workspace
                    cand: str | None = None
                    mj = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
                    if isinstance(mj, dict):
                        cand = mj.get("region") or mj.get("source_region") or mj.get("data_residency") or mj.get("residency")
                    if not cand and asset.location:
                        cand = str(asset.location)
                    if cand:
                        src_region = _norm_region(cand)
            except Exception as exc:  # noqa: BLE001
                logger.debug("check_cross_border asset lookup failed: %s", exc)

        cross = _is_cross_border(src_region, proc_region)
        requires_approval = bool(cross)
        reason: str | None = None
        if cross:
            reason = f"cross-border flagged — source_region '{src_region}' != processing_region '{proc_region}' — approval required"
        else:
            if src_region and proc_region and src_region.strip().lower() == proc_region.strip().lower():
                reason = f"no cross-border — regions match ({src_region})"
            elif not src_region and not proc_region:
                reason = "no cross-border — no region specified"
            else:
                reason = f"no cross-border — source '{src_region}' processing '{proc_region}'"

        result: dict[str, Any] = {
            "cross_border": cross,
            "source_region": src_region,
            "processing_region": proc_region,
            "requires_approval": requires_approval,
            "reason": reason,
            "processor_id": str(processor_id).strip() if processor_id and str(processor_id).strip() else None,
            "asset_id": str(asset_id).strip() if asset_id and str(asset_id).strip() else None,
            "tenant": tenant_s,
        }

        # audit when flagged
        if cross:
            _audit(tenant_s, "system", "governance.processor.cross_border.flagged", str(processor_id) if processor_id else (str(asset_id) if asset_id else ""), {"source_region": src_region, "processing_region": proc_region, "reason": reason})

        return result

    # ── access grants (third-party) ─────────────────────────────────────

    async def grant_access(
        self,
        db: AsyncSession,
        tenant: str,
        processor_id: str,
        resource: str,
        scope: dict | str | None = None,
        granted_by: str | None = None,
        expires_at: datetime | None = None,
    ) -> GovernanceProcessor:
        """Grant third-party data access to a processor.

        Appends to GovernanceProcessor.access_grants JSON list.

        Args:
            tenant: tenant scope.
            processor_id: processor id.
            resource: resource being granted (asset_id, table, etc.).
            scope: scope descriptor (dict or str).
            granted_by: actor who granted.
            expires_at: optional expiry (timezone-aware preferred).

        Returns:
            Updated GovernanceProcessor row.
        """
        if not tenant or not processor_id or not resource:
            raise ValueError("tenant, processor_id and resource are required")
        if not str(resource).strip():
            raise ValueError("resource cannot be empty")

        row = await self.get_processor(db, tenant, processor_id)
        if row is None:
            raise ValueError(f"processor '{processor_id}' not found for tenant '{tenant}'")
        if row.status == "revoked":
            raise ValueError("cannot grant access — processor is revoked")

        # normalize scope
        if scope is None:
            scope_norm: Any = {}
        elif isinstance(scope, dict):
            scope_norm = dict(scope)
        elif isinstance(scope, str):
            scope_norm = {"scope": scope.strip()} if scope.strip() else {}
        else:
            scope_norm = {"scope": str(scope)}

        # validate expires_at if provided
        expires: datetime | None = None
        if expires_at is not None:
            if not isinstance(expires_at, datetime):
                raise ValueError("expires_at must be a datetime")
            expires = expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)

        grant: dict[str, Any] = {
            "grant_id": str(uuid.uuid4()),
            "resource": str(resource).strip(),
            "scope": scope_norm,
            "granted_by": str(granted_by).strip() if granted_by and str(granted_by).strip() else "system",
            "granted_at": _utc_now().isoformat(),
            "expires_at": expires.isoformat() if expires else None,
            "status": "active",
        }

        grants = list(row.access_grants or [])
        grants.append(grant)
        row.access_grants = grants

        await db.flush()
        await db.refresh(row)

        _audit(str(tenant).strip(), str(granted_by).strip() if granted_by and str(granted_by).strip() else "system", "governance.processor.access_granted", str(row.id), {"resource": str(resource).strip(), "grant_id": grant["grant_id"]})
        return row

    async def revoke_grant(
        self,
        db: AsyncSession,
        tenant: str,
        processor_id: str,
        grant_id: str,
        revoked_by: str | None = None,
        reason: str | None = None,
    ) -> GovernanceProcessor:
        """Revoke a single access grant (by grant_id).

        Args:
            tenant: tenant scope.
            processor_id: processor id.
            grant_id: grant identifier (grant_id).
            revoked_by: actor.
            reason: optional reason.

        Returns:
            Updated GovernanceProcessor row.
        """
        if not tenant or not processor_id or not grant_id:
            raise ValueError("tenant, processor_id and grant_id are required")

        row = await self.get_processor(db, tenant, processor_id)
        if row is None:
            raise ValueError(f"processor '{processor_id}' not found for tenant '{tenant}'")

        grants = list(row.access_grants or [])
        found = False
        for g in grants:
            if not isinstance(g, dict):
                continue
            if g.get("grant_id") == str(grant_id).strip():
                if g.get("status") == "revoked":
                    found = True
                    break
                g["status"] = "revoked"
                g["revoked_at"] = _utc_now().isoformat()
                g["revoked_by"] = str(revoked_by).strip() if revoked_by and str(revoked_by).strip() else "system"
                if reason and str(reason).strip():
                    g["revoke_reason"] = str(reason).strip()
                found = True
                break

        if not found:
            raise ValueError(f"grant '{grant_id}' not found for processor '{processor_id}'")

        row.access_grants = grants
        await db.flush()
        await db.refresh(row)

        _audit(str(tenant).strip(), str(revoked_by).strip() if revoked_by and str(revoked_by).strip() else "system", "governance.processor.grant_revoked", str(row.id), {"grant_id": str(grant_id).strip(), "reason": reason})
        return row

    async def list_access_grants(
        self,
        db: AsyncSession,
        tenant: str,
        processor_id: str,
        active_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List access grants for a processor (tenant-scoped).

        Args:
            tenant: tenant scope.
            processor_id: processor id.
            active_only: if True, only grants with status active and not expired.

        Returns:
            List of grant dicts (empty list if none).
        """
        if not tenant or not processor_id:
            raise ValueError("tenant and processor_id are required")
        row = await self.get_processor(db, tenant, processor_id)
        if row is None:
            raise ValueError(f"processor '{processor_id}' not found for tenant '{tenant}'")

        grants = list(row.access_grants or [])
        # filter out non-grant audit entries (those with action key)
        grant_entries = [g for g in grants if isinstance(g, dict) and "grant_id" in g]

        if not active_only:
            return grant_entries

        now = _utc_now()
        out: list[dict[str, Any]] = []
        for g in grant_entries:
            if g.get("status") == "revoked":
                continue
            exp_str = g.get("expires_at")
            if exp_str:
                try:
                    exp = datetime.fromisoformat(str(exp_str).replace("Z", "+00:00"))
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=timezone.utc)
                    if now > exp:
                        continue
                except Exception:
                    pass
            out.append(g)
        return out

    async def list_grants(
        self,
        db: AsyncSession,
        tenant: str,
        processor_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List grants across all or single processor (tenant-scoped convenience).

        Args:
            tenant: tenant scope.
            processor_id: if provided, only grants for that processor.

        Returns:
            List of grant dicts enriched with processor_id.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()

        if processor_id and str(processor_id).strip():
            grants = await self.list_access_grants(db, tenant_s, str(processor_id).strip(), active_only=False)
            # enrich
            for g in grants:
                g.setdefault("processor_id", str(processor_id).strip())
            return grants

        # all processors
        processors = await self.list_processors(db, tenant_s)
        all_grants: list[dict[str, Any]] = []
        for p in processors:
            grants = list(p.access_grants or [])
            for g in grants:
                if isinstance(g, dict) and "grant_id" in g:
                    enriched = dict(g)
                    enriched.setdefault("processor_id", str(p.id))
                    enriched.setdefault("provider", p.provider)
                    all_grants.append(enriched)
        return all_grants


processor_service = ProcessorService()
