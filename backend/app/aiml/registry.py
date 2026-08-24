"""Volume 58 — AIModelRegistryService (tenant-scoped, AsyncSession).

Covers AIModelRegistry + AIModelVersion with immutable-version guarantee
and never-silently-replace-approved-version rule.

Statuses: DRAFT / APPROVED / ACTIVE / DEPRECATED / RETIRED / BLOCKED
Risk   : LOW / MEDIUM / HIGH / CRITICAL
Types  : foundation / fine-tuned / embedding / rag / agent / custom (open)

Tenant isolation: every read/write scoped to tenant (except id-only
mutators that resolve tenant from the row and preserve it).

Audit: best-effort via app.iam.audit_service — never raises.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aiml.models import AIModelRegistry, AIModelVersion
from app.core.exceptions import ConflictError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)


# ── constants ──────────────────────────────────────────────────────────

_VALID_STATUSES: set[str] = {"DRAFT", "APPROVED", "ACTIVE", "DEPRECATED", "RETIRED", "BLOCKED"}
_APPROVED_STATUSES: set[str] = {"APPROVED", "ACTIVE"}
_VALID_RISK_LEVELS: set[str] = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
_VALID_TYPES: set[str] = {"foundation", "fine-tuned", "embedding", "rag", "agent", "custom", "chat", "completion", "multimodal"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    """Best-effort audit; never raises, never logs raw secrets."""
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        safe_details: dict = {}
        if details:
            for k, v in details.items():
                if k in ("raw_value", "secret", "prompt", "content", "value", "match"):
                    continue
                if isinstance(v, dict) and "raw_value" in v:
                    v = {ik: iv for ik, iv in v.items() if ik != "raw_value"}
                safe_details[k] = v
        try:
            audit_service.log(
                tenant,
                actor,
                "user",
                action,
                "ai_model_registry",
                resource_id,
                "success",
                safe_details,
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "ai_model_registry", resource_id, "success", safe_details)  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(message=f"invalid UUID: {value} — {exc}") from exc


class AIModelRegistryService:
    """Tenant-scoped registry for AI models and immutable versions."""

    # ── register ───────────────────────────────────────────────────────

    async def register_model(
        self,
        db: AsyncSession,
        tenant: str,
        provider: str,
        name: str,
        version: str,
        type: str = "foundation",  # noqa: A002 - spec requires param name `type`
        capabilities: dict | None = None,
        license: str | None = None,  # noqa: A002
        region: str | None = None,
        risk_level: str = "LOW",
        owner: str | None = None,
    ) -> AIModelRegistry:
        """Register a new model version.

        Never silently replaces an approved version — if a row with the same
        (tenant, provider, name, version) exists and its status is
        APPROVED/ACTIVE a ConflictError is raised. Any duplicate at all
        raises ConflictError to avoid silent overwrite; caller must use
        explicit update/version APIs.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant id (required, non-empty).
            provider: provider key (e.g. openai, anthropic) required.
            name: model name required.
            version: model version string required.
            type: model type (foundation etc).
            capabilities: dict of capability flags.
            license: license identifier.
            region: deployment region.
            risk_level: LOW/MEDIUM/HIGH/CRITICAL.
            owner: owner identity.

        Returns: persisted AIModelRegistry row.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        if not provider or not str(provider).strip():
            raise ValidationError(message="provider is required")
        if not name or not str(name).strip():
            raise ValidationError(message="name is required")
        if not version or not str(version).strip():
            raise ValidationError(message="version is required")

        tenant_s = str(tenant).strip()
        provider_s = str(provider).strip()
        name_s = str(name).strip()
        version_s = str(version).strip()
        type_s = str(type).strip().lower() if type else "foundation"
        if type_s not in _VALID_TYPES:
            # allow custom types but normalise to known set if possible
            # if unknown, keep as provided but warn
            logger.debug("unknown model type '%s' — storing as-is", type_s)
        risk_s = str(risk_level).strip().upper() if risk_level else "LOW"
        if risk_s not in _VALID_RISK_LEVELS:
            raise ValidationError(message=f"invalid risk_level '{risk_level}'; allowed: {sorted(_VALID_RISK_LEVELS)}")

        capabilities_s: dict = dict(capabilities) if capabilities else {}

        # duplicate check — tenant + provider + name + version unique
        stmt = select(AIModelRegistry).where(
            AIModelRegistry.tenant == tenant_s,
            AIModelRegistry.provider == provider_s,
            AIModelRegistry.name == name_s,
            AIModelRegistry.version == version_s,
        )
        result = await db.execute(stmt)
        existing = result.scalars().first()
        if existing is not None:
            if existing.status in _APPROVED_STATUSES:
                raise ConflictError(f"never silently replace approved version: {provider_s}/{name_s}:{version_s} is {existing.status}")
            raise ConflictError(f"model already exists: {provider_s}/{name_s}:{version_s} (status={existing.status})")

        # model_id composite for human readability; not the PK
        composite_id = f"{provider_s}/{name_s}:{version_s}"[:128]

        row = AIModelRegistry(
            tenant=tenant_s,
            provider=provider_s,
            name=name_s,
            version=version_s,
            type=type_s,
            capabilities=capabilities_s,
            license=license,
            region=str(region).strip() if region else None,
            status="DRAFT",
            risk_level=risk_s,
            owner=str(owner).strip() if owner else None,
            model_id=composite_id,
        )
        # ensure id default via TimestampMixin
        db.add(row)
        await db.flush()
        await db.refresh(row)
        _audit(tenant_s, owner or "system", "aiml.model.registered", str(row.id), {"provider": provider_s, "name": name_s, "version": version_s, "type": type_s})
        logger.info("registered model %s tenant=%s", composite_id, tenant_s)
        return row

    # ── get ────────────────────────────────────────────────────────────

    async def get_model(
        self,
        db: AsyncSession,
        tenant: str,
        model_id: str | uuid.UUID,
    ) -> AIModelRegistry | None:
        """Fetch model by PK (uuid) scoped to tenant.

        Returns None if not found or tenant mismatch (isolation).
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        pk = _parse_uuid(model_id)
        stmt = select(AIModelRegistry).where(
            AIModelRegistry.id == pk,
            AIModelRegistry.tenant == tenant_s,
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    # ── list ───────────────────────────────────────────────────────────

    async def list_models(
        self,
        db: AsyncSession,
        tenant: str,
        filters: dict | None = None,
    ) -> list[AIModelRegistry]:
        """List models for tenant with optional equality filters.

        Supported filter keys: provider, name, version, type, status,
        risk_level, region, owner, license, capability (checks key in
        capabilities JSON — treated as equality on that key).
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        filters = dict(filters) if filters else {}

        stmt = select(AIModelRegistry).where(AIModelRegistry.tenant == tenant_s)

        # direct column filters
        for key in ("provider", "name", "version", "type", "status", "risk_level", "region", "owner", "license"):
            val = filters.get(key)
            if val is None or val == "":
                continue
            col = getattr(AIModelRegistry, key, None)
            if col is not None:
                stmt = stmt.where(col == val)

        # capabilities sub-filter: e.g. filters["capabilities"] == {"chat": True} or filters["capability"] == "chat"
        cap = filters.get("capabilities")
        if isinstance(cap, dict) and cap:
            # best-effort: filter in python post-query for JSON containment (portable across backends)
            # we apply narrow DB filter only via provider/name etc and do json filter after
            pass
        cap_key = filters.get("capability")
        if isinstance(cap_key, str) and cap_key.strip():
            pass

        stmt = stmt.order_by(AIModelRegistry.created_at.desc())
        result = await db.execute(stmt)
        rows = list(result.scalars().all())

        # post-filter for JSON containment if requested
        if isinstance(cap, dict) and cap:
            filtered: list[AIModelRegistry] = []
            for r in rows:
                caps = r.capabilities or {}
                if all(caps.get(k) == v for k, v in cap.items()):
                    filtered.append(r)
            rows = filtered
        if isinstance(cap_key, str) and cap_key.strip():
            ck = cap_key.strip()
            rows = [r for r in rows if (r.capabilities or {}).get(ck)]

        return rows

    # ── update_status ──────────────────────────────────────────────────

    async def update_status(
        self,
        db: AsyncSession,
        model_id: str | uuid.UUID,
        status: str,
    ) -> AIModelRegistry:
        """Update model status (no tenant param — resolves tenant from row).

        Validates status value and persists. Audit best-effort.
        """
        if not status or not str(status).strip():
            raise ValidationError(message="status is required")
        status_s = str(status).strip().upper()
        if status_s not in _VALID_STATUSES:
            raise ValidationError(message=f"invalid status '{status}'; allowed: {sorted(_VALID_STATUSES)}")

        pk = _parse_uuid(model_id)
        stmt = select(AIModelRegistry).where(AIModelRegistry.id == pk)
        result = await db.execute(stmt)
        row: AIModelRegistry | None = result.scalars().first()
        if row is None:
            raise NotFoundError(resource="AIModelRegistry", identifier=str(pk))

        old = row.status
        row.status = status_s
        await db.flush()
        await db.refresh(row)
        _audit(row.tenant, row.owner or "system", "aiml.model.status_updated", str(row.id), {"old_status": old, "new_status": status_s})
        logger.info("model %s status %s -> %s", row.model_id, old, status_s)
        return row

    # ── deprecate / retire / block ─────────────────────────────────────

    async def deprecate(
        self,
        db: AsyncSession,
        model_id: str | uuid.UUID,
    ) -> AIModelRegistry:
        """Mark model DEPRECATED."""
        return await self.update_status(db, model_id, "DEPRECATED")

    async def retire(
        self,
        db: AsyncSession,
        model_id: str | uuid.UUID,
    ) -> AIModelRegistry:
        """Mark model RETIRED."""
        return await self.update_status(db, model_id, "RETIRED")

    async def block(
        self,
        db: AsyncSession,
        model_id: str | uuid.UUID,
    ) -> AIModelRegistry:
        """Mark model BLOCKED (policy/security)."""
        return await self.update_status(db, model_id, "BLOCKED")

    # ── version ────────────────────────────────────────────────────────

    async def create_version(
        self,
        db: AsyncSession,
        model_id: str | uuid.UUID,
        version: str,
        artifact: str | None = None,
    ) -> AIModelVersion:
        """Create an immutable version for a model.

        Immutable check: if a version with the same (model_id, version)
        already exists and immutable=True, raise ConflictError — never
        mutate an immutable version. Duplicate version string always raises
        ConflictError.

        Args:
            db: AsyncSession.
            model_id: parent AIModelRegistry PK (UUID).
            version: version string for the artifact.
            artifact: artifact URI/path (e.g. s3://... or registry ref).

        Returns: persisted AIModelVersion.
        """
        if not version or not str(version).strip():
            raise ValidationError(message="version is required")
        version_s = str(version).strip()
        pk = _parse_uuid(model_id)

        # parent must exist
        stmt = select(AIModelRegistry).where(AIModelRegistry.id == pk)
        result = await db.execute(stmt)
        parent: AIModelRegistry | None = result.scalars().first()
        if parent is None:
            raise NotFoundError(resource="AIModelRegistry", identifier=str(pk))

        # duplicate version for this model
        stmt2 = select(AIModelVersion).where(
            AIModelVersion.model_id == pk,
            AIModelVersion.version == version_s,
        )
        result2 = await db.execute(stmt2)
        existing: AIModelVersion | None = result2.scalars().first()
        if existing is not None:
            if existing.immutable:
                raise ConflictError(f"immutable version already exists: {pk}:{version_s} — cannot replace")
            raise ConflictError(f"version already exists: {pk}:{version_s}")

        row = AIModelVersion(
            model_id=pk,
            version=version_s,
            artifact=str(artifact).strip() if artifact else None,
            immutable=True,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        _audit(parent.tenant, parent.owner or "system", "aiml.model.version_created", str(row.id), {"model_id": str(pk), "version": version_s, "artifact": artifact})
        logger.info("created version %s for model %s", version_s, parent.model_id)
        return row


registry_service = AIModelRegistryService()
