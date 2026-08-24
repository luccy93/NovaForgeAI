"""Volume 57 — ConsentService (tenant-scoped consent ledger + withdrawal).

Provides:
  - record_consent — creates GovernanceConsent row
  - withdraw_consent — sets status withdrawn, identifies affected processing,
                       records exceptions if retention/legal-hold prevents deletion
  - list_consents  — tenant-scoped listing, optionally filtered by subject
  - get_consent    — tenant-scoped fetch by id

Tenant isolation enforced. Audit best-effort. No placeholders.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datagov.models import GovernanceConsent, GovernanceDataAsset

logger = logging.getLogger(__name__)


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
                "governance_consent",
                resource_id,
                "success",
                details or {},
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "governance_consent", resource_id, "success", details or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


VALID_CONSENT_STATUSES: set[str] = {"granted", "withdrawn", "denied", "expired", "pending"}


async def _is_under_hold(db: AsyncSession, tenant: str, asset_id: str, resource: str | None = None) -> bool:
    """Best-effort legal-hold check (mirrors RetentionService logic, self-contained).

    Returns True if any active GovernanceLegalHold matches the asset.
    """
    try:
        from app.datagov.models import GovernanceLegalHold  # local import to avoid circular

        stmt = select(GovernanceLegalHold).where(
            GovernanceLegalHold.tenant == tenant,
            GovernanceLegalHold.released_at.is_(None),
        )
        result = await db.execute(stmt)
        holds = list(result.scalars().all())
        if not holds:
            return False
        asset_id_s = str(asset_id).strip()
        resource_s = str(resource).strip() if resource else None
        for h in holds:
            scope = str(h.scope).strip() if h.scope else ""
            if not scope:
                continue
            if scope in ("*", "all"):
                return True
            if scope == asset_id_s:
                return True
            if resource_s and scope == resource_s:
                return True
            if scope in (f"asset:{asset_id_s}", f"asset_id:{asset_id_s}"):
                return True
            if resource_s and scope in (f"resource:{resource_s}", f"resource_id:{resource_s}"):
                return True
            if asset_id_s in scope or scope in asset_id_s:
                return True
            if resource_s and (resource_s in scope or scope in resource_s):
                return True
        return False
    except Exception as exc:  # noqa: BLE001
        logger.debug("hold check failed: %s", exc)
        return False


async def _find_affected_assets(
    db: AsyncSession,
    tenant: str,
    subject: str,
    purpose: str,
    scope: dict | None,
) -> list[GovernanceDataAsset]:
    """Identify assets affected by a consent (subject/purpose/scope).

    Matches on tenant and heuristic subject/purpose linkage across data assets.
    Checks asset_id, resource, owner, and metadata_json for subject/purpose
    substrings. tenant-scoped.
    """
    try:
        stmt = select(GovernanceDataAsset).where(GovernanceDataAsset.tenant == tenant)
        result = await db.execute(stmt)
        assets = list(result.scalars().all())
    except Exception as exc:  # noqa: BLE001
        logger.debug("affected asset query failed: %s", exc)
        return []

    subject_s = str(subject).strip().lower() if subject else ""
    purpose_s = str(purpose).strip().lower() if purpose else ""
    scope_str = str(scope).lower() if scope else ""

    affected: list[GovernanceDataAsset] = []
    for asset in assets:
        # collect searchable fields
        hay_fields: list[str] = []
        try:
            hay_fields.append(str(asset.asset_id or "").lower())
            hay_fields.append(str(asset.resource or "").lower())
            hay_fields.append(str(asset.owner or "").lower())
            hay_fields.append(str(getattr(asset, "type", "") or "").lower())
            mj = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
            if isinstance(mj, dict):
                # stringify metadata for substring match
                hay_fields.append(str(mj).lower())
                # also check explicit keys
                for key in ("subject", "data_subject", "purpose", "consent_purpose", "owner", "email", "user_id"):
                    if key in mj and mj[key]:
                        hay_fields.append(str(mj[key]).lower())
            # scope matching: if consent scope contains resource/type hint, match directly
            if scope and isinstance(scope, dict):
                # explicit asset_ids list in scope
                if "asset_ids" in scope and isinstance(scope["asset_ids"], list):
                    if asset.asset_id in scope["asset_ids"]:
                        affected.append(asset)
                        continue
                if "resource" in scope and scope["resource"]:
                    if str(scope["resource"]).lower() == str(asset.resource).lower():
                        affected.append(asset)
                        continue
                if "type" in scope and scope["type"]:
                    if str(scope["type"]).lower() == str(getattr(asset, "type", "")).lower():
                        affected.append(asset)
                        continue
                # scope category matching (marketing, analytics, personalization etc)
                if "categories" in scope and isinstance(scope["categories"], list):
                    for cat in scope["categories"]:
                        if cat and str(cat).lower() in " ".join(hay_fields):
                            affected.append(asset)
                            break
                    if asset in affected:
                        continue
        except Exception:
            continue

        hay = " ".join(hay_fields)
        matched = False
        if subject_s and subject_s in hay:
            matched = True
        if purpose_s and purpose_s in hay:
            matched = True
        # if purpose is generic like marketing, also match if asset metadata purpose equals
        if not matched and subject_s:
            # fallback: subject email substring in owner/resource
            if "@" in subject_s:
                local = subject_s.split("@")[0]
                if local and local in hay:
                    matched = True
        if matched:
            affected.append(asset)

    # de-duplicate by id while preserving order
    seen: set[str] = set()
    uniq: list[GovernanceDataAsset] = []
    for a in affected:
        key = str(a.id)
        if key not in seen:
            seen.add(key)
            uniq.append(a)
    return uniq


class ConsentService:
    """Tenant-scoped consent ledger."""

    async def record_consent(
        self,
        db: AsyncSession,
        tenant: str,
        subject: str,
        purpose: str,
        scope: dict | None = None,
        version: str = "1.0",
        status: str = "granted",
    ) -> GovernanceConsent:
        """Create a GovernanceConsent row.

        Args:
            tenant: tenant scope (required).
            subject: data-subject identifier (required, non-empty).
            purpose: purpose of processing (required, non-empty).
            scope: scope dict describing data categories / resources.
            version: consent text/policy version (default 1.0).
            status: one of {granted, withdrawn, denied, expired, pending}.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()

        if not subject or not str(subject).strip():
            raise ValueError("subject is required and cannot be empty")
        subject_s = str(subject).strip()

        if not purpose or not str(purpose).strip():
            raise ValueError("purpose is required and cannot be empty")
        purpose_s = str(purpose).strip()

        version_s = str(version).strip() if version and str(version).strip() else "1.0"

        status_norm = str(status).strip().lower() if status and str(status).strip() else "granted"
        if status_norm not in VALID_CONSENT_STATUSES:
            raise ValueError(f"invalid status '{status}'; allowed: {sorted(VALID_CONSENT_STATUSES)}")

        scope_dict: dict = dict(scope) if isinstance(scope, dict) else ({"scope": str(scope).strip()} if isinstance(scope, str) and scope.strip() else {} if scope is None else {"scope": scope})  # type: ignore
        if not isinstance(scope_dict, dict):
            scope_dict = {"scope": str(scope_dict)}

        row = GovernanceConsent(
            tenant=tenant_s,
            subject=subject_s,
            purpose=purpose_s,
            scope=scope_dict,
            version=version_s,
            status=status_norm,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)

        _audit(tenant_s, subject_s, "governance.consent.recorded", str(row.id), {"purpose": purpose_s, "version": version_s, "status": status_norm})
        return row

    async def withdraw_consent(
        self,
        db: AsyncSession,
        consent_id: str,
        actor: str,
    ) -> dict[str, Any]:
        """Withdraw consent, identify affected processing, record retention exceptions.

        Sets GovernanceConsent.status to ``withdrawn``. Identifies affected
        assets via subject/purpose/scope heuristics and checks each against
        active legal holds / retention policies. Where deletion is prevented
        by retention, an exception entry is created on the returned dict and
        a GovernanceException row is best-effort persisted.

        Args:
            consent_id: GovernanceConsent id (uuid string).
            actor: actor performing withdrawal.

        Returns:
            dict with keys:
              - consent: the updated GovernanceConsent row
              - affected_assets: list[GovernanceDataAsset] (also serialized as
                                 affected_asset_ids for convenience)
              - affected_asset_ids: list[str]
              - exceptions: list[dict] describing retention blocks
        """
        if not consent_id or not str(consent_id).strip():
            raise ValueError("consent_id is required")
        if not actor or not str(actor).strip():
            raise ValueError("actor is required")
        actor_s = str(actor).strip()

        pid = _parse_uuid(str(consent_id).strip())
        if pid is not None:
            stmt = select(GovernanceConsent).where(GovernanceConsent.id == pid)
        else:
            stmt = select(GovernanceConsent).where(GovernanceConsent.id == consent_id)  # type: ignore
        result = await db.execute(stmt)
        row: GovernanceConsent | None = result.scalars().first()
        if row is None:
            raise ValueError(f"consent '{consent_id}' not found")

        if row.status == "withdrawn":
            # idempotent — still report affected assets
            affected = await _find_affected_assets(db, row.tenant, row.subject, row.purpose, row.scope if isinstance(row.scope, dict) else None)
            return {
                "consent": row,
                "affected_assets": affected,
                "affected_asset_ids": [a.asset_id for a in affected],
                "exceptions": [],
            }

        row.status = "withdrawn"
        await db.flush()

        # identify affected processing
        affected_assets = await _find_affected_assets(
            db, row.tenant, row.subject, row.purpose, row.scope if isinstance(row.scope, dict) else None
        )

        exceptions: list[dict[str, Any]] = []

        # for each affected asset, check if retention/legal-hold prevents deletion
        for asset in affected_assets:
            try:
                under_hold = await _is_under_hold(db, row.tenant, asset.asset_id, getattr(asset, "resource", None))
            except Exception:
                under_hold = False
            if under_hold:
                exc_entry: dict[str, Any] = {
                    "asset_id": asset.asset_id,
                    "reason": "retention/legal-hold prevents deletion after consent withdrawal",
                    "scope": {"consent_id": str(row.id), "subject": row.subject, "purpose": row.purpose},
                    "retention_blocked": True,
                }
                exceptions.append(exc_entry)
                # best-effort persist to governance_exceptions
                try:
                    from app.datagov.models import GovernanceException as _Exc  # local import

                    exc_row = _Exc(
                        tenant=row.tenant,
                        policy_id=None,
                        resource=asset.asset_id,
                        reason="consent withdrawal blocked — legal hold / retention",
                        scope={"consent_id": str(row.id), "asset_id": asset.asset_id, "subject": row.subject},
                        owner=actor_s,
                        approval=None,
                        expires_at=None,
                    )
                    db.add(exc_row)
                    await db.flush()
                    exc_entry["exception_id"] = str(exc_row.id)
                except Exception as ex:  # noqa: BLE001
                    logger.debug("failed to persist consent withdrawal exception: %s", ex)

        # if retention exceptions exist, stash on consent scope for audit trace
        if exceptions:
            try:
                scope_with_note = dict(row.scope or {})
                scope_with_note["_withdrawal_exceptions"] = exceptions
                scope_with_note["_withdrawn_at"] = _utc_now().isoformat()
                scope_with_note["_withdrawn_by"] = actor_s
                row.scope = scope_with_note
                await db.flush()
            except Exception as ex:  # noqa: BLE001
                logger.debug("failed to annotate consent with exceptions: %s", ex)

        await db.refresh(row)

        _audit(
            row.tenant,
            actor_s,
            "governance.consent.withdrawn",
            str(row.id),
            {
                "subject": row.subject,
                "purpose": row.purpose,
                "affected_count": len(affected_assets),
                "exceptions_count": len(exceptions),
            },
        )

        return {
            "consent": row,
            "affected_assets": affected_assets,
            "affected_asset_ids": [a.asset_id for a in affected_assets],
            "exceptions": exceptions,
        }

    async def list_consents(
        self,
        db: AsyncSession,
        tenant: str,
        subject: str | None = None,
    ) -> list[GovernanceConsent]:
        """List consents for tenant, optionally filtered by subject."""
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()
        stmt = select(GovernanceConsent).where(GovernanceConsent.tenant == tenant_s)
        if subject is not None and str(subject).strip() != "":
            stmt = stmt.where(GovernanceConsent.subject == str(subject).strip())
        stmt = stmt.order_by(GovernanceConsent.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_consent(
        self,
        db: AsyncSession,
        tenant: str,
        consent_id: str,
    ) -> GovernanceConsent | None:
        """Fetch single consent tenant-scoped."""
        if not tenant or not consent_id:
            raise ValueError("tenant and consent_id are required")
        tenant_s = str(tenant).strip()
        pid = _parse_uuid(str(consent_id).strip())
        if pid is not None:
            stmt = select(GovernanceConsent).where(
                GovernanceConsent.tenant == tenant_s,
                GovernanceConsent.id == pid,
            )
        else:
            stmt = select(GovernanceConsent).where(
                GovernanceConsent.tenant == tenant_s,
                GovernanceConsent.id == consent_id,  # type: ignore
            )
        result = await db.execute(stmt)
        return result.scalars().first()


consent_service = ConsentService()
