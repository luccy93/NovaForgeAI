"""Volume 56 — ReleaseLockService (NovaForge).

Additive, real implementation using AsyncSession + SQLAlchemy.
Handles exclusive locks per (tenant, service, environment) with expiry
and concurrent-conflict detection.

Model: app.release.models.ReleaseLock
Unique constraint: ix_release_locks_tenant_service_env (tenant, service, environment)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.release.models import ReleaseLock

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class ReleaseLockService:
    """Exclusive environment lock service (Volume 56).

    Guarantees:
        * One active lock per (tenant, service, environment) — enforced by
          DB unique index + application-level check.
        * Expiry via ``expires_at`` — expired locks are treated as absent
          and lazily cleaned up.
        * Concurrent detection — second acquire on same service/env while
          an unexpired lock exists raises ``ValueError`` (409-style conflict).
        * Audit trail via metadata_json / change tracking on ``ReleaseLock``
          and explicit ``locked_by`` / ``reason``.
    """

    # ---------------------------------------------------------------
    # Acquire
    # ---------------------------------------------------------------

    async def acquire_lock(
        self,
        db: AsyncSession,
        tenant: str,
        service: str,
        env: str | None = None,
        locked_by: str | None = None,
        reason: str = "",
        ttl_seconds: int | None = None,
        environment: str | None = None,
        **kwargs,
    ) -> ReleaseLock:
        """Acquire an exclusive lock for (tenant, service, env).

        Args:
            db: AsyncSession
            tenant: tenant / organization identifier (non-empty)
            service: service identifier (non-empty)
            env: environment name e.g. ``production`` / ``staging``
            locked_by: actor acquiring the lock
            reason: human-readable reason for the lock
            ttl_seconds: optional TTL; when provided ``expires_at`` is set to
                         now + ttl_seconds. ``None`` or ``0`` means no expiry.

        Returns:
            Persisted ``ReleaseLock``.

        Raises:
            ValueError: on validation or when a conflicting unexpired lock exists.
        """
        # alias handling: support both env and environment
        if env is None:
            env = environment or kwargs.get("environment") or kwargs.get("env")
        if locked_by is None:
            locked_by = kwargs.get("locked_by") or kwargs.get("owner")
        if not tenant or not tenant.strip():
            raise ValueError("tenant must be a non-empty string")
        if not service or not service.strip():
            raise ValueError("service must be a non-empty string")
        if not env or not env.strip():
            raise ValueError("env must be a non-empty string")
        if not locked_by or not locked_by.strip():
            raise ValueError("locked_by must be a non-empty string")

        tenant = tenant.strip()
        service = service.strip()
        env = env.strip()
        locked_by = locked_by.strip()
        reason = str(reason or "")

        if ttl_seconds is not None:
            try:
                ttl = int(ttl_seconds)
            except Exception:
                raise ValueError("ttl_seconds must be an integer or None")
            if ttl < 0:
                raise ValueError("ttl_seconds must be >= 0")
        else:
            ttl = None

        expires_at: datetime | None = None
        if ttl is not None and ttl > 0:
            expires_at = _now() + timedelta(seconds=ttl)

        # ---- check for existing lock on same (tenant, service, env) ----
        stmt = select(ReleaseLock).where(
            ReleaseLock.tenant == tenant,
            ReleaseLock.service == service,
            ReleaseLock.environment == env,
        ).limit(1)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            exp = _ensure_aware(getattr(existing, "expires_at", None))
            if exp is not None and exp < _now():
                # expired — lazy cleanup: remove stale lock so we can re-acquire
                logger.info(
                    "acquire_lock: removing expired lock id=%s tenant=%s service=%s env=%s expired_at=%s",
                    existing.id, tenant, service, env, exp.isoformat(),
                )
                await db.delete(existing)
                await db.flush()
                existing = None
            else:
                # unexpired — concurrent conflict
                raise ValueError(
                    f"conflict: environment already locked: tenant={tenant!r} service={service!r} "
                    f"env={env!r} locked_by={existing.locked_by!r} reason={existing.reason!r} "
                    f"expires_at={exp.isoformat() if exp else 'never'} (lock id {existing.id})"
                )

        # ---- create lock ----
        lock = ReleaseLock(
            tenant=tenant,
            service=service,
            environment=env,
            locked_by=locked_by,
            reason=reason,
            expires_at=expires_at,
        )
        db.add(lock)
        try:
            await db.flush()
        except IntegrityError as exc:
            # handle race: unique constraint violation from concurrent insert
            await db.rollback()
            # re-check
            stmt2 = select(ReleaseLock).where(
                ReleaseLock.tenant == tenant,
                ReleaseLock.service == service,
                ReleaseLock.environment == env,
            ).limit(1)
            result2 = await db.execute(stmt2)
            conflicting = result2.scalar_one_or_none()
            if conflicting is not None:
                exp2 = _ensure_aware(getattr(conflicting, "expires_at", None))
                if exp2 is not None and exp2 < _now():
                    await db.delete(conflicting)
                    await db.flush()
                    # retry once
                    lock = ReleaseLock(
                        tenant=tenant,
                        service=service,
                        environment=env,
                        locked_by=locked_by,
                        reason=reason,
                        expires_at=expires_at,
                    )
                    db.add(lock)
                    await db.flush()
                    logger.info(
                        "acquire_lock: race resolved by cleaning expired lock tenant=%s service=%s env=%s",
                        tenant, service, env,
                    )
                    return lock
                raise ValueError(
                    f"conflict: concurrent acquire detected for tenant={tenant!r} service={service!r} env={env!r} "
                    f"locked_by={conflicting.locked_by!r}"
                ) from exc
            raise ValueError(f"failed to acquire lock due to integrity error: {exc}") from exc

        logger.info(
            "acquired lock id=%s tenant=%s service=%s env=%s locked_by=%s ttl=%s expires_at=%s",
            lock.id, tenant, service, env, locked_by, ttl, expires_at.isoformat() if expires_at else "never",
        )
        return lock

    # ---------------------------------------------------------------
    # Release
    # ---------------------------------------------------------------

    async def release_lock(
        self,
        db: AsyncSession,
        lock_id: uuid.UUID | str,
        actor: str,
    ) -> None:
        """Release a lock by id.

        Only the lock owner or an actor with explicit permission should
        release, but we allow any actor and audit the action — separation
        of duties is enforced at the orchestrator layer. We do enforce that
        the lock exists and is not already expired (expired locks are
        already considered released but we still clean them).

        Args:
            db: AsyncSession
            lock_id: ReleaseLock.id
            actor: actor performing release (audited)

        Raises:
            ValueError: if lock not found.
        """
        if not actor or not str(actor).strip():
            raise ValueError("actor must be a non-empty string")
        actor = str(actor).strip()

        try:
            lid = uuid.UUID(str(lock_id)) if not isinstance(lock_id, uuid.UUID) else lock_id
        except Exception as exc:
            raise ValueError(f"invalid lock_id {lock_id!r}: {exc}") from exc

        lock = await db.get(ReleaseLock, lid)
        if lock is None:
            raise ValueError(f"lock {lid} not found")

        # optional ownership warning (not hard block, but logged)
        if lock.locked_by != actor:
            logger.warning(
                "release_lock: actor %r releasing lock owned by %r (lock id=%s tenant=%s service=%s env=%s)",
                actor, lock.locked_by, lock.id, lock.tenant, lock.service, lock.environment,
            )

        await db.delete(lock)
        await db.flush()
        logger.info(
            "released lock id=%s tenant=%s service=%s env=%s released_by=%s previous_owner=%s",
            lid, lock.tenant, lock.service, lock.environment, actor, lock.locked_by,
        )

    # ---------------------------------------------------------------
    # Check
    # ---------------------------------------------------------------

    async def check_lock(
        self,
        db: AsyncSession,
        tenant: str,
        service: str,
        env: str | None = None,
        environment: str | None = None,
        **kwargs,
    ) -> ReleaseLock | None:
        """Check whether an active (unexpired) lock exists for the tuple.

        Expired locks are treated as absent and are lazily removed.

        Returns:
            ``ReleaseLock`` if an active lock exists, else ``None``.
        """
        if env is None:
            env = environment or kwargs.get("environment") or kwargs.get("env")
        if not tenant or not tenant.strip():
            raise ValueError("tenant must be a non-empty string")
        if not service or not service.strip():
            raise ValueError("service must be a non-empty string")
        if not env or not env.strip():
            raise ValueError("env must be a non-empty string")

        tenant = tenant.strip()
        service = service.strip()
        env = env.strip()

        stmt = select(ReleaseLock).where(
            ReleaseLock.tenant == tenant,
            ReleaseLock.service == service,
            ReleaseLock.environment == env,
        ).limit(1)
        result = await db.execute(stmt)
        lock = result.scalar_one_or_none()
        if lock is None:
            return None

        exp = _ensure_aware(getattr(lock, "expires_at", None))
        if exp is not None and exp < _now():
            # expired — cleanup
            logger.info(
                "check_lock: cleaning expired lock id=%s tenant=%s service=%s env=%s expired_at=%s",
                lock.id, tenant, service, env, exp.isoformat(),
            )
            await db.delete(lock)
            await db.flush()
            return None

        return lock

    # ---------------------------------------------------------------
    # List
    # ---------------------------------------------------------------

    async def list_locks(
        self,
        db: AsyncSession,
        tenant: str,
    ) -> list[ReleaseLock]:
        """List all *active* (unexpired) locks for a tenant.

        Expired locks are filtered out and lazily cleaned. Returned locks
        are ordered by creation time descending (newest first).

        Args:
            db: AsyncSession
            tenant: tenant identifier

        Returns:
            List of ``ReleaseLock``.
        """
        if not tenant or not tenant.strip():
            raise ValueError("tenant must be a non-empty string")
        tenant = tenant.strip()

        stmt = select(ReleaseLock).where(ReleaseLock.tenant == tenant).order_by(ReleaseLock.created_at.desc())
        result = await db.execute(stmt)
        locks = list(result.scalars().all())

        active: list[ReleaseLock] = []
        now = _now()
        for lock in locks:
            exp = _ensure_aware(getattr(lock, "expires_at", None))
            if exp is not None and exp < now:
                # lazily clean
                try:
                    await db.delete(lock)
                except Exception as exc:
                    logger.debug("list_locks: failed to clean expired lock %s: %s", lock.id, exc)
                continue
            active.append(lock)

        # flush deletions if any expired were removed
        if len(active) != len(locks):
            try:
                await db.flush()
            except Exception:
                pass

        return active
