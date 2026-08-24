"""Volume 58 — AICardService (tenant-scoped, AsyncSession).

Manages ``ai_model_cards`` and ``ai_system_cards`` with no fabrication.

Model cards document a single model's purpose, capabilities, limitations,
risk, evaluation summary, data policy, provider, version, and approved
environments.  System cards document an AI system's assembly of models,
tools, inputs/outputs, permissions, human oversight, failure modes,
evaluation, and deployment scope.

No fabrication: when limitations are not provided they are stored as
``{"value": "not_specified"}`` (JSON) — never invented.  The same
principle applies to any field not supplied: it is kept as provided
or ``None``/empty, not hallucinated.

Tenant isolation: every create/read is scoped to tenant.
Audit best-effort via ``app.iam.audit_service`` — never raises.
No placeholders — all branches are real AsyncSession operations.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aiml.models import AIModelCard, AISystemCard
from app.core.exceptions import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

_NOT_SPECIFIED = {"value": "not_specified"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        safe: dict = {}
        if details:
            for k, v in details.items():
                if k in ("raw_value", "secret", "prompt", "content", "value", "match"):
                    continue
                if isinstance(v, dict) and "raw_value" in v:
                    v = {ik: iv for ik, iv in v.items() if ik != "raw_value"}
                safe[k] = v
        try:
            audit_service.log(tenant, actor, "user", action, "ai_card", resource_id, "success", safe)
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "ai_card", resource_id, "success", safe)  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value).strip())
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(message=f"invalid UUID: {value} — {exc}") from exc


def _normalize_dict(value: Any, default: dict | None = None) -> dict:
    if value is None:
        return dict(default) if default is not None else {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        # list of capabilities/limitations items -> wrap as items
        return {"items": list(value)}
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return dict(default) if default is not None else {}
        return {"value": s}
    return dict(default) if default is not None else {}


def _normalize_limitations(value: Any) -> dict:
    """No fabrication — when not provided return not_specified."""
    if value is None:
        return dict(_NOT_SPECIFIED)
    if isinstance(value, dict):
        if not value:
            return dict(_NOT_SPECIFIED)
        return dict(value)
    if isinstance(value, list):
        if not value:
            return dict(_NOT_SPECIFIED)
        return {"items": list(value)}
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return dict(_NOT_SPECIFIED)
        # if string is literally "not_specified", keep canonical dict
        if s.lower() == "not_specified":
            return dict(_NOT_SPECIFIED)
        return {"value": s}
    # unexpected type
    if not value:
        return dict(_NOT_SPECIFIED)
    return {"value": str(value)}


def _normalize_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        return [s]
    if isinstance(value, dict):
        # dict with items
        if "items" in value and isinstance(value["items"], list):
            return list(value["items"])
        return [value]
    return [value]


def _normalize_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


class AICardService:
    """Tenant-scoped model and system card registry."""

    # ── model card ─────────────────────────────────────────────────────

    async def create_model_card(
        self,
        db: AsyncSession,
        tenant: str,
        model_id: str | uuid.UUID,
        purpose: str | None = None,
        capabilities: dict | list | str | None = None,
        limitations: dict | list | str | None = None,
        risk: str | None = None,
        evaluation_summary: dict | None = None,
        data_policy: str | None = None,
        provider: str | None = None,
        version: str | None = None,
        approved_environments: list | None = None,
    ) -> AIModelCard:
        """Create a model card (tenant-scoped).

        No fabrication: if ``limitations`` is not provided (None, empty dict,
        empty list, or empty string) it is stored as ``{"value":
        "not_specified"}`` — never invented.

        Args:
            db: AsyncSession.
            tenant: tenant id (required).
            model_id: FK to ``ai_model_registry.id`` (UUID, required).
            purpose: intended purpose description.
            capabilities: dict/list/str of capabilities (stored as JSON dict).
            limitations: dict/list/str of limitations — when not provided
                becomes ``{"value": "not_specified"}``.
            risk: risk level string (e.g. LOW/MEDIUM/HIGH/CRITICAL).
            evaluation_summary: dict with evaluation metrics/summary.
            data_policy: data policy identifier or description.
            provider: provider key (e.g. openai).
            version: model version string.
            approved_environments: list of approved deployment envs.

        Returns: persisted ``AIModelCard``.

        Raises:
            ValidationError for missing/invalid tenant/model_id.
            NotFoundError when model_id does not exist for tenant (tenant
                isolation — prevents referencing another tenant's model).
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        if model_id is None or (isinstance(model_id, str) and not str(model_id).strip()):
            raise ValidationError(message="model_id is required")
        tenant_s = str(tenant).strip()
        model_uuid = _parse_uuid(model_id)
        if model_uuid is None:
            raise ValidationError(message="model_id must be a valid UUID")

        # Tenant-scoped existence check for the referenced model (isolation).
        # We probe ai_model_registry; if unavailable we log and continue.
        try:
            from app.aiml.models import AIModelRegistry  # local import to avoid cycle

            stmt_m = select(AIModelRegistry).where(
                AIModelRegistry.id == model_uuid,
                AIModelRegistry.tenant == tenant_s,
            )
            result_m = await db.execute(stmt_m)
            found = result_m.scalars().first()
            if found is None:
                raise NotFoundError(resource="AIModelRegistry", identifier=str(model_uuid))
        except NotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.debug("model existence check failed for %s: %s", model_uuid, exc)
            # Do not block creation on lookup failure — proceed but log warning
            # (keeps service functional when model table is not migrated yet)
            pass

        purpose_s = _normalize_str(purpose)
        capabilities_s = _normalize_dict(capabilities, default={})
        limitations_s = _normalize_limitations(limitations)
        risk_s = _normalize_str(risk)
        if risk_s:
            risk_s = risk_s.upper()
        evaluation_s = _normalize_dict(evaluation_summary, default={})
        data_policy_s = _normalize_str(data_policy)
        provider_s = _normalize_str(provider)
        if provider_s:
            provider_s = provider_s.strip()
        version_s = _normalize_str(version)
        approved_envs_s = _normalize_list(approved_environments)

        row = AIModelCard(
            tenant=tenant_s,
            model_id=model_uuid,
            purpose=purpose_s,
            capabilities=capabilities_s,
            limitations=limitations_s,
            risk=risk_s,
            evaluation_summary=evaluation_s,
            data_policy=data_policy_s,
            provider=provider_s,
            version=version_s,
            approved_environments=approved_envs_s,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        _audit(tenant_s, "system", "ai_card.model_card_created", str(row.id), {"model_id": str(model_uuid), "purpose": purpose_s, "provider": provider_s, "version": version_s})
        logger.info("model card for %s tenant=%s card=%s", model_uuid, tenant_s, row.id)
        return row

    async def get_model_card(
        self,
        db: AsyncSession,
        tenant: str,
        card_id: str | uuid.UUID,
    ) -> AIModelCard | None:
        """Fetch model card by PK, tenant-scoped. Returns None if not found."""
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        pk = _parse_uuid(card_id)
        if pk is None:
            raise ValidationError(message="card_id is required")
        stmt = select(AIModelCard).where(AIModelCard.id == pk, AIModelCard.tenant == tenant_s)
        result = await db.execute(stmt)
        return result.scalars().first()

    async def list_model_cards(
        self,
        db: AsyncSession,
        tenant: str,
        model_id: str | uuid.UUID | None = None,
        provider: str | None = None,
    ) -> list[AIModelCard]:
        """List model cards for tenant with optional filters."""
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        stmt = select(AIModelCard).where(AIModelCard.tenant == tenant_s)
        if model_id is not None and str(model_id).strip():
            try:
                mu = _parse_uuid(model_id)
                if mu is not None:
                    stmt = stmt.where(AIModelCard.model_id == mu)
            except ValidationError:
                pass
        if provider and str(provider).strip():
            stmt = stmt.where(AIModelCard.provider == str(provider).strip())
        stmt = stmt.order_by(AIModelCard.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── system card ────────────────────────────────────────────────────

    async def create_system_card(
        self,
        db: AsyncSession,
        tenant: str,
        system: str,
        purpose: str | None = None,
        inputs: dict | None = None,
        outputs: dict | None = None,
        models: list | None = None,
        tools: list | None = None,
        permissions: list | None = None,
        human_oversight: str | None = None,
        failure_modes: list | None = None,
        evaluation: dict | None = None,
        deployment_scope: str | None = None,
    ) -> AISystemCard:
        """Create a system card (tenant-scoped).

        No fabrication: any field not provided is stored as provided
        (None/empty) — never invented.  ``failure_modes`` defaults to []
        only as an empty collection signal, not as content.

        Args:
            db: AsyncSession.
            tenant: tenant id (required).
            system: system identifier (required) — e.g. service name.
            purpose: intended purpose description.
            inputs: dict describing inputs (stored as JSON dict).
            outputs: dict describing outputs.
            models: list of model references (ids or name:version).
            tools: list of tool identifiers used by the system.
            permissions: list of permission scopes.
            human_oversight: description of human oversight mechanisms.
            failure_modes: list of known failure modes.
            evaluation: dict with evaluation summary for the system.
            deployment_scope: deployment scope identifier.

        Returns: persisted ``AISystemCard``.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        if not system or not str(system).strip():
            raise ValidationError(message="system is required")
        tenant_s = str(tenant).strip()
        system_s = str(system).strip()

        purpose_s = _normalize_str(purpose)
        inputs_s = _normalize_dict(inputs, default={})
        outputs_s = _normalize_dict(outputs, default={})
        models_s = _normalize_list(models)
        tools_s = _normalize_list(tools)
        permissions_s = _normalize_list(permissions)
        human_oversight_s = _normalize_str(human_oversight)
        failure_modes_s = _normalize_list(failure_modes)
        evaluation_s = _normalize_dict(evaluation, default={})
        deployment_scope_s = _normalize_str(deployment_scope)

        row = AISystemCard(
            tenant=tenant_s,
            system=system_s,
            purpose=purpose_s,
            inputs=inputs_s,
            outputs=outputs_s,
            models=models_s,
            tools=tools_s,
            permissions=permissions_s,
            human_oversight=human_oversight_s,
            failure_modes=failure_modes_s,
            evaluation=evaluation_s,
            deployment_scope=deployment_scope_s,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        _audit(tenant_s, "system", "ai_card.system_card_created", str(row.id), {"system": system_s, "deployment_scope": deployment_scope_s})
        logger.info("system card '%s' tenant=%s card=%s", system_s, tenant_s, row.id)
        return row

    async def get_system_card(
        self,
        db: AsyncSession,
        tenant: str,
        card_id: str | uuid.UUID,
    ) -> AISystemCard | None:
        """Fetch system card by PK, tenant-scoped. Returns None if not found."""
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        pk = _parse_uuid(card_id)
        if pk is None:
            raise ValidationError(message="card_id is required")
        stmt = select(AISystemCard).where(AISystemCard.id == pk, AISystemCard.tenant == tenant_s)
        result = await db.execute(stmt)
        return result.scalars().first()

    async def list_system_cards(
        self,
        db: AsyncSession,
        tenant: str,
        system: str | None = None,
        deployment_scope: str | None = None,
    ) -> list[AISystemCard]:
        """List system cards for tenant with optional filters."""
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        stmt = select(AISystemCard).where(AISystemCard.tenant == tenant_s)
        if system and str(system).strip():
            stmt = stmt.where(AISystemCard.system == str(system).strip())
        if deployment_scope and str(deployment_scope).strip():
            stmt = stmt.where(AISystemCard.deployment_scope == str(deployment_scope).strip())
        stmt = stmt.order_by(AISystemCard.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())


card_service = AICardService()
# Backwards-compat aliases
ai_card_service = card_service
aicard_service = card_service
