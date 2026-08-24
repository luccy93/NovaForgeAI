"""Volume 57 — ExportService (expiring scoped exports, hashed tokens, no permanent URLs).

Provides:
  - create_export — creates GovernanceExport with sha256(random token)[:32],
                    expires_at = now + ttl_hours, status ready
  - get_export    — tenant-scoped fetch by id
  - verify_token  — checks hash and expiry, returns export or None
  - revoke        — revokes export (status=revoked)

Security: raw token is never stored — only token_hash (sha256 hex digest
truncated to 32 chars). Links always expire (default 24h). Audit best-effort.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datagov.models import GovernanceExport

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
                "governance_export",
                resource_id,
                "success",
                details or {},
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "governance_export", resource_id, "success", details or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _hash_token(token: str) -> str:
    """sha256 hex[:32] — truncated for storage per spec."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


VALID_FORMATS: set[str] = {"json", "csv", "parquet", "zip", "xlsx", "xml"}


class ExportService:
    """Tenant-scoped expiring export service."""

    async def create_export(
        self,
        db: AsyncSession,
        tenant: str,
        request_id: str | None = None,
        requester: str | None = None,
        scope: dict | list | str | None = None,
        data_sources: list | None = None,
        format: str = "json",  # noqa: A002
        ttl_hours: int = 24,
    ) -> GovernanceExport:
        """Create a scoped, expiring export.

        Args:
            tenant: tenant scope (required).
            request_id: optional GovernanceDataRequest id this export fulfils.
            requester: actor requesting export (required).
            scope: export scope description (dict recommended).
            data_sources: list of source identifiers (e.g., rag, kg, billing).
            format: export format (json/csv/parquet/zip etc).
            ttl_hours: time-to-live in hours (default 24, must be >0).

        Returns:
            GovernanceExport row with an ephemeral attribute ``_raw_token``
            containing the plaintext token (only available at creation time;
            never persisted). Stored column ``token_hash`` holds sha256(token)[:32].
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()

        if not requester or not str(requester).strip():
            raise ValueError("requester is required")
        requester_s = str(requester).strip()

        # validate ttl
        try:
            ttl = int(ttl_hours) if ttl_hours is not None else 24
        except Exception:
            raise ValueError("ttl_hours must be an integer > 0")
        if ttl <= 0:
            raise ValueError("ttl_hours must be > 0")

        # normalize format
        fmt = str(format).strip().lower() if format else "json"
        # allow any non-empty format but record if outside known set
        if not fmt:
            raise ValueError("format is required")
        # keep format value even if not in VALID_FORMATS — config-driven

        # normalize scope
        if scope is None:
            scope_dict: dict = {}
        elif isinstance(scope, dict):
            scope_dict = dict(scope)
        elif isinstance(scope, list):
            scope_dict = {"scope": list(scope)}
        elif isinstance(scope, str):
            scope_dict = {"scope": scope.strip()} if scope.strip() else {}
        else:
            scope_dict = {"scope": str(scope)}

        # normalize data_sources
        if data_sources is None:
            ds_list: list = []
        elif isinstance(data_sources, list):
            ds_list = list(data_sources)
        else:
            ds_list = [str(data_sources)]

        # validate request_id if provided — ensure it exists and tenant matches when possible
        request_uuid: uuid.UUID | None = None
        if request_id is not None and str(request_id).strip() != "":
            pid = _parse_uuid(str(request_id).strip())
            if pid is not None:
                request_uuid = pid
                # verify request exists and is not cross-tenant (best-effort)
                try:
                    from app.datagov.models import GovernanceDataRequest as _Req

                    stmt = select(_Req).where(_Req.id == pid)
                    result = await db.execute(stmt)
                    req_row = result.scalars().first()
                    if req_row is not None and hasattr(req_row, "tenant") and req_row.tenant != tenant_s:
                        raise ValueError("request_id does not belong to tenant")
                except ValueError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.debug("request_id validation skipped: %s", exc)
            else:
                # non-uuid request_id — store as string in scope but not as FK
                # we cannot store non-uuid in Uuid FK column; keep request_uuid None
                # and stash original in scope
                scope_dict.setdefault("request_id_original", str(request_id).strip())
                request_uuid = None

        # generate token — never store raw value
        raw_token = secrets.token_urlsafe(32)
        token_hash = _hash_token(raw_token)
        expires_at = _utc_now() + timedelta(hours=ttl)

        row = GovernanceExport(
            tenant=tenant_s,
            request_id=request_uuid,
            requester=requester_s,
            scope=scope_dict,
            data_sources=ds_list,
            format=fmt,
            token_hash=token_hash,
            expires_at=expires_at,
            status="ready",
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)

        # ephemeral plaintext token — not persisted, only on in-memory instance
        # attach for caller to build one-time URL; after this it is gone
        try:
            object.__setattr__(row, "_raw_token", raw_token)  # type: ignore[attr-defined]
            object.__setattr__(row, "_token", raw_token)  # type: ignore[attr-defined]
            # also expose as .token for convenience without persisting
        except Exception:
            pass
        # also return token via row attribute so callers can do row._raw_token
        _audit(
            tenant_s,
            requester_s,
            "governance.export.created",
            str(row.id),
            {"format": fmt, "ttl_hours": ttl, "expires_at": expires_at.isoformat(), "request_id": str(request_uuid) if request_uuid else None},
        )
        return row

    async def get_export(
        self,
        db: AsyncSession,
        export_id: str,
        tenant: str | None = None,
    ) -> GovernanceExport | None:
        """Fetch export by id, optionally tenant-scoped.

        Args:
            export_id: GovernanceExport id (uuid string).
            tenant: if provided, enforces tenant isolation.
        """
        if not export_id or not str(export_id).strip():
            raise ValueError("export_id is required")
        pid = _parse_uuid(str(export_id).strip())
        if pid is not None:
            stmt = select(GovernanceExport).where(GovernanceExport.id == pid)
        else:
            stmt = select(GovernanceExport).where(GovernanceExport.id == export_id)  # type: ignore
        if tenant and str(tenant).strip():
            stmt = stmt.where(GovernanceExport.tenant == str(tenant).strip())
        result = await db.execute(stmt)
        row: GovernanceExport | None = result.scalars().first()
        if row is None:
            return None
        # enforce expiry lazily — if expired, mark as expired if still ready
        if row.expires_at is not None:
            exp = row.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if _utc_now() > exp and row.status not in ("expired", "revoked"):
                # do not automatically persist status change without caller intent?
                # we update best-effort so verify_token will fail closed
                try:
                    row.status = "expired"
                    await db.flush()
                    await db.refresh(row)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("lazy expiry update failed: %s", exc)
        return row

    async def verify_token(
        self,
        db: AsyncSession,
        token: str,
    ) -> GovernanceExport | None:
        """Verify a plaintext export token.

        Checks sha256(token)[:32] against stored token_hash and that
        expires_at is in the future and status is not revoked/expired.
        Returns the matching export or None if invalid/expired/revoked.
        Never logs the raw token.
        """
        if not token or not str(token).strip():
            raise ValueError("token is required")
        token_s = str(token).strip()
        token_hash = _hash_token(token_s)

        stmt = select(GovernanceExport).where(GovernanceExport.token_hash == token_hash)
        result = await db.execute(stmt)
        row: GovernanceExport | None = result.scalars().first()
        if row is None:
            return None

        # revoked check — fail closed
        if row.status in ("revoked", "cancelled"):
            return None

        # expiry check — never permanent URLs
        if row.expires_at is None:
            # treat as expired if no expiry (fail closed)
            return None
        exp = row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if _utc_now() > exp:
            # best-effort mark expired
            try:
                if row.status != "expired":
                    row.status = "expired"
                    await db.flush()
                    await db.refresh(row)
            except Exception as exc:  # noqa: BLE001
                logger.debug("expiry mark failed: %s", exc)
            return None

        # token valid and not expired
        return row

    async def revoke(
        self,
        db: AsyncSession,
        export_id: str,
        tenant: str | None = None,
    ) -> GovernanceExport:
        """Revoke an export (immediate invalidation).

        Args:
            export_id: GovernanceExport id.
            tenant: optional tenant isolation.

        Returns:
            Revoked row.
        """
        if not export_id or not str(export_id).strip():
            raise ValueError("export_id is required")

        pid = _parse_uuid(str(export_id).strip())
        if pid is not None:
            stmt = select(GovernanceExport).where(GovernanceExport.id == pid)
        else:
            stmt = select(GovernanceExport).where(GovernanceExport.id == export_id)  # type: ignore
        if tenant and str(tenant).strip():
            stmt = stmt.where(GovernanceExport.tenant == str(tenant).strip())

        result = await db.execute(stmt)
        row: GovernanceExport | None = result.scalars().first()
        if row is None:
            raise ValueError(f"export '{export_id}' not found")

        if tenant and str(tenant).strip() and row.tenant != str(tenant).strip():
            raise ValueError(f"export '{export_id}' not found for tenant")

        if row.status == "revoked":
            # idempotent — already revoked
            return row

        row.status = "revoked"
        # optionally clear token_hash to prevent any future verification via hash
        # we keep hash for audit but revoke ensures verify_token fails; clearing is defense-in-depth
        # do not null it so audit retains link — status is source of truth
        await db.flush()
        await db.refresh(row)

        _audit(row.tenant, "system", "governance.export.revoked", str(row.id), {"format": row.format})
        return row

    async def list_exports(
        self,
        db: AsyncSession,
        tenant: str,
    ) -> list[GovernanceExport]:
        """List exports for tenant (tenant-scoped)."""
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        stmt = select(GovernanceExport).where(GovernanceExport.tenant == str(tenant).strip()).order_by(GovernanceExport.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())


export_service = ExportService()
