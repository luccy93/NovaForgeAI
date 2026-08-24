"""Volume 58 — AIProviderRegistryService (tenant-scoped, AsyncSession).

Manages AIProviderRegistry rows. Compliance check enforces no-claim-
without-evidence: a provider's pricing/security/contract claims must
be backed by evidence fields in contract_metadata / security_status.

Tenant scope: display_name unique per tenant via provider key; listing
and retrieval always filter by tenant. Availability values:
AVAILABLE / DEGRADED / UNAVAILABLE / UNKNOWN  — only AVAILABLE is
considered healthy (DEGRADED/UNAVAILABLE/UNKNOWN treated unavailable).

Audit: best-effort via app.iam.audit_service — never raises.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aiml.models import AIProviderRegistry
from app.core.exceptions import ConflictError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)


_VALID_AVAILABILITY: set[str] = {"AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN", "MAINTENANCE"}
_VALID_SECURITY: set[str] = {"UNKNOWN", "PENDING", "VERIFIED", "FAILED", "CERTIFIED", "COMPLIANT", "NON_COMPLIANT"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        safe_details: dict = {}
        if details:
            for k, v in details.items():
                if k in ("raw_value", "secret", "prompt", "content", "value", "match"):
                    continue
                safe_details[k] = v
        try:
            audit_service.log(
                tenant,
                actor,
                "user",
                action,
                "ai_provider_registry",
                resource_id,
                "success",
                safe_details,
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "ai_provider_registry", resource_id, "success", safe_details)  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(message=f"invalid UUID: {value} — {exc}") from exc


class AIProviderRegistryService:
    """Tenant-scoped provider registry."""

    # ── register ───────────────────────────────────────────────────────

    async def register_provider(
        self,
        db: AsyncSession,
        tenant: str,
        provider: str,
        display_name: str,
        models: list | None = None,
        regions: list | None = None,
        pricing: dict | None = None,
        data_processing_policy: dict | None = None,
        availability: str = "AVAILABLE",
        security_status: str = "UNKNOWN",
        contract_metadata: dict | None = None,
    ) -> AIProviderRegistry:
        """Register or upsert a provider for a tenant.

        If a row with the same (tenant, provider) already exists it is
        updated (upsert) — tenant isolation prevents cross-tenant overwrite.
        If the existing row is for a different tenant it is not visible
        (provider column is globally unique at DB level but we treat it
        as tenant-scoped by checking tenant first; duplicate provider for
        another tenant raises ConflictError to avoid leaking).

        Args:
            db: AsyncSession.
            tenant: tenant id required.
            provider: provider key (e.g. openai, anthropic).
            display_name: human display name.
            models: list of model names offered.
            regions: list of region identifiers.
            pricing: dict (e.g. cost per 1k tokens).
            data_processing_policy: dict describing data handling.
            availability: AVAILABLE / DEGRADED / UNAVAILABLE / UNKNOWN.
            security_status: UNKNOWN/PENDING/VERIFIED etc.
            contract_metadata: dict with contract evidence.

        Returns: persisted AIProviderRegistry.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        if not provider or not str(provider).strip():
            raise ValidationError(message="provider is required")
        if not display_name or not str(display_name).strip():
            raise ValidationError(message="display_name is required")

        tenant_s = str(tenant).strip()
        provider_s = str(provider).strip().lower()
        display_s = str(display_name).strip()
        avail_s = str(availability).strip().upper() if availability else "AVAILABLE"
        if avail_s not in _VALID_AVAILABILITY:
            raise ValidationError(message=f"invalid availability '{availability}'; allowed: {sorted(_VALID_AVAILABILITY)}")
        sec_s = str(security_status).strip().upper() if security_status else "UNKNOWN"
        # allow any but normalise; validate against known set only if wanted
        if sec_s not in _VALID_SECURITY:
            logger.debug("unknown security_status '%s' — storing as-is", sec_s)

        models_s: list = list(models) if models else []
        regions_s: list = list(regions) if regions else []
        pricing_s: dict = dict(pricing) if pricing else {}
        dpp_s: dict = dict(data_processing_policy) if data_processing_policy else {}
        contract_s: dict = dict(contract_metadata) if contract_metadata else {}

        # tenant-scoped lookup first
        stmt = select(AIProviderRegistry).where(
            AIProviderRegistry.tenant == tenant_s,
            AIProviderRegistry.provider == provider_s,
        )
        result = await db.execute(stmt)
        existing: AIProviderRegistry | None = result.scalars().first()

        if existing is not None:
            # upsert — update fields
            existing.display_name = display_s
            existing.models = models_s
            existing.regions = regions_s
            existing.pricing = pricing_s
            existing.data_processing_policy = dpp_s
            existing.availability = avail_s
            existing.security_status = sec_s
            existing.contract_metadata = contract_s
            await db.flush()
            await db.refresh(existing)
            _audit(tenant_s, "system", "aiml.provider.updated", str(existing.id), {"provider": provider_s, "availability": avail_s})
            logger.info("updated provider %s tenant=%s", provider_s, tenant_s)
            return existing

        # check global collision (provider unique) — another tenant already owns this key
        stmt2 = select(AIProviderRegistry).where(AIProviderRegistry.provider == provider_s)
        result2 = await db.execute(stmt2)
        collision: AIProviderRegistry | None = result2.scalars().first()
        if collision is not None and collision.tenant != tenant_s:
            raise ConflictError(f"provider key '{provider_s}' already registered for another tenant")

        row = AIProviderRegistry(
            tenant=tenant_s,
            provider=provider_s,
            display_name=display_s,
            models=models_s,
            regions=regions_s,
            pricing=pricing_s,
            data_processing_policy=dpp_s,
            availability=avail_s,
            security_status=sec_s,
            contract_metadata=contract_s,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        _audit(tenant_s, "system", "aiml.provider.registered", str(row.id), {"provider": provider_s, "display_name": display_s})
        logger.info("registered provider %s tenant=%s", provider_s, tenant_s)
        return row

    # ── get ────────────────────────────────────────────────────────────

    async def get_provider(
        self,
        db: AsyncSession,
        tenant: str,
        provider: str | uuid.UUID,
    ) -> AIProviderRegistry | None:
        """Fetch provider by provider key or PK, scoped to tenant.

        If provider looks like a UUID we treat it as PK id, otherwise as
        provider key. Returns None if tenant mismatch.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()

        # try UUID path first
        try:
            maybe_uuid = uuid.UUID(str(provider))
            stmt = select(AIProviderRegistry).where(
                AIProviderRegistry.id == maybe_uuid,
                AIProviderRegistry.tenant == tenant_s,
            )
            result = await db.execute(stmt)
            row = result.scalars().first()
            if row is not None:
                return row
            # fall through to key lookup if not found by id
        except Exception:
            pass

        provider_s = str(provider).strip().lower()
        stmt2 = select(AIProviderRegistry).where(
            AIProviderRegistry.tenant == tenant_s,
            AIProviderRegistry.provider == provider_s,
        )
        result2 = await db.execute(stmt2)
        return result2.scalars().first()

    # ── list ───────────────────────────────────────────────────────────

    async def list_providers(
        self,
        db: AsyncSession,
        tenant: str,
        filters: dict | None = None,
    ) -> list[AIProviderRegistry]:
        """List providers for tenant with optional equality filters.

        Supported filter keys: provider, display_name, availability,
        security_status, region (checks membership in regions list),
        model (checks membership in models list).
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        filters = dict(filters) if filters else {}

        stmt = select(AIProviderRegistry).where(AIProviderRegistry.tenant == tenant_s)

        for key in ("provider", "display_name", "availability", "security_status"):
            val = filters.get(key)
            if val is None or val == "":
                continue
            col = getattr(AIProviderRegistry, key, None)
            if col is not None:
                # provider is stored lowercased
                if key == "provider":
                    val = str(val).strip().lower()
                stmt = stmt.where(col == val)

        stmt = stmt.order_by(AIProviderRegistry.created_at.desc())
        result = await db.execute(stmt)
        rows = list(result.scalars().all())

        # post-filter for list membership (regions/models are JSON arrays)
        region_filter = filters.get("region") or filters.get("regions")
        if isinstance(region_filter, str) and region_filter.strip():
            rf = region_filter.strip()
            rows = [r for r in rows if rf in (r.regions or [])]
        model_filter = filters.get("model") or filters.get("models")
        if isinstance(model_filter, str) and model_filter.strip():
            mf = model_filter.strip()
            rows = [r for r in rows if mf in (r.models or [])]

        return rows

    # ── update_availability ────────────────────────────────────────────

    async def update_availability(
        self,
        db: AsyncSession,
        tenant: str,
        provider: str | uuid.UUID,
        availability: str,
    ) -> AIProviderRegistry:
        """Update provider availability (tenant-scoped)."""
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        if not availability or not str(availability).strip():
            raise ValidationError(message="availability is required")
        avail_s = str(availability).strip().upper()
        if avail_s not in _VALID_AVAILABILITY:
            raise ValidationError(message=f"invalid availability '{availability}'; allowed: {sorted(_VALID_AVAILABILITY)}")

        row = await self.get_provider(db, tenant_s, provider)
        if row is None:
            raise NotFoundError(resource="AIProviderRegistry", identifier=str(provider))

        old = row.availability
        row.availability = avail_s
        await db.flush()
        await db.refresh(row)
        _audit(tenant_s, "system", "aiml.provider.availability_updated", str(row.id), {"provider": row.provider, "old": old, "new": avail_s})
        logger.info("provider %s availability %s -> %s", row.provider, old, avail_s)
        return row

    # ── check_compliance ───────────────────────────────────────────────

    async def check_compliance(
        self,
        db: AsyncSession,
        tenant: str,
        provider: str | uuid.UUID,
    ) -> dict[str, Any]:
        """Check provider compliance — no claim without evidence.

        Validates that claims in pricing/security_status/contract_metadata
        are backed by evidence fields. Returns a compliance report dict:

        {
            "compliant": bool,
            "provider": str,
            "checks": { ... per-claim results ... },
            "violations": [ ... ],
            "reason": str
        }

        Never trusts a claim that lacks an evidence entry.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()

        row = await self.get_provider(db, tenant_s, provider)
        if row is None:
            raise NotFoundError(resource="AIProviderRegistry", identifier=str(provider))

        violations: list[str] = []
        checks: dict[str, Any] = {}

        # 1. Security status claim requires evidence
        sec = (row.security_status or "UNKNOWN").upper()
        if sec in ("VERIFIED", "CERTIFIED", "COMPLIANT"):
            evidence = (row.contract_metadata or {}).get("security_evidence") or (row.contract_metadata or {}).get("evidence")
            has_evidence = bool(evidence)
            # also check data_processing_policy for evidence blob
            if not has_evidence:
                has_evidence = bool((row.data_processing_policy or {}).get("evidence") or (row.data_processing_policy or {}).get("audit_report"))
            checks["security_claim"] = {"claimed": sec, "evidence_present": has_evidence}
            if not has_evidence:
                violations.append(f"security_status '{sec}' claimed without evidence (contract_metadata.security_evidence missing)")

        # 2. Pricing claims require evidence / contract reference
        pricing = row.pricing or {}
        if pricing:
            # if pricing asserts specific rates, require contract or pricing_evidence
            contract = row.contract_metadata or {}
            has_pricing_evidence = bool(contract.get("pricing_evidence") or contract.get("evidence") or contract.get("contract_id") or contract.get("pricing_verified"))
            checks["pricing_claim"] = {"has_pricing": True, "evidence_present": has_pricing_evidence, "keys": list(pricing.keys())}
            if not has_pricing_evidence:
                violations.append("pricing claimed without contract_metadata pricing_evidence/contract_id")

        # 3. Data processing policy claims require policy evidence
        dpp = row.data_processing_policy or {}
        if dpp:
            # if policy claims GDPR/SOC2 etc, need evidence
            claimed_standards = [k for k in ("gdpr", "soc2", "hipaa", "iso27001", "ccpa") if dpp.get(k) or str(dpp.get("certification", "")).lower() == k]
            if claimed_standards:
                has_dpp_evidence = bool(dpp.get("evidence") or dpp.get("audit_report") or (row.contract_metadata or {}).get("dpp_evidence"))
                checks["dpp_claim"] = {"standards": claimed_standards, "evidence_present": has_dpp_evidence}
                if not has_dpp_evidence:
                    violations.append(f"data_processing_policy claims {claimed_standards} without evidence")

        # 4. Availability claim — DEGRADED/UNAVAILABLE must have incident reference if claimed AVAILABLE
        # (no extra check; just record)
        checks["availability"] = {"value": row.availability, "is_available": row.availability == "AVAILABLE"}

        # 5. Contract metadata overall — if any contract_id, must have verification timestamp
        contract = row.contract_metadata or {}
        if contract.get("contract_id") and not contract.get("verified_at") and not contract.get("evidence"):
            # soft violation — warn but not fail unless security claimed
            checks["contract_completeness"] = {"contract_id": contract.get("contract_id"), "verified": False}

        compliant = len(violations) == 0
        reason = "compliant" if compliant else "; ".join(violations)
        if compliant:
            _audit(tenant_s, "system", "aiml.provider.compliance_passed", str(row.id), {"provider": row.provider})
        else:
            _audit(tenant_s, "system", "aiml.provider.compliance_failed", str(row.id), {"provider": row.provider, "violations": violations})

        return {
            "compliant": compliant,
            "provider": row.provider,
            "provider_id": str(row.id),
            "tenant": tenant_s,
            "checks": checks,
            "violations": violations,
            "reason": reason,
        }


provider_service = AIProviderRegistryService()
