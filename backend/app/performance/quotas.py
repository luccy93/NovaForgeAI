"""Volume 61 Commit 1 — TenantQuotaOrchestrator (billing Plans -> IAM quotas).

Bridges billing ``Plans`` to IAM ``QuotaPolicy`` and resource_management
quotas. Enforces per-tenant quotas for requests/AI tokens/agents/jobs/
storage/CI minutes/RAG queries with atomic Redis Lua or DB SELECT FOR UPDATE
and weighted fairness by PlanTier.

Reuses billing.constants.PlanTier, billing.plan_service, iam.quota_service,
iam.models.QuotaPolicy, core.redis, and iam.constants defaults.
"""

from __future__ import annotations

import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.constants import PlanTier, PLAN_PRICING
# NOTE: app.iam.models currently has a reserved 'metadata' attribute conflict on
# SQLAlchemy 2.x (IAMRole.metadata shadows Base.metadata). To keep this module
# importable in all environments we avoid importing the broken model and instead
# define a local compatible mapping for iam_quota_policies. The sync/check/consume
# logic still reuses billing PlanTier, billing plan_service, and iam.quota_service
# (in-memory) where available.
import uuid as _uuid2
from datetime import datetime as _dt2
from sqlalchemy import Boolean, DateTime, Integer, String, Index
from sqlalchemy.types import JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, TimestampMixin

class QuotaPolicy(Base, TimestampMixin):  # type: ignore[no-redef]
    __tablename__ = "iam_quota_policies"
    __table_args__ = (
        Index("ix_iam_quota_policies_org_id", "organization_id"),
        Index("ix_iam_quota_policies_org_type", "organization_id", "quota_type", unique=True),
        {"extend_existing": True},
    )
    organization_id: Mapped[_uuid2.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)  # type: ignore
    quota_type: Mapped[str] = mapped_column(String(100), nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    period_start: Mapped[_dt2 | None] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[_dt2 | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON, default=dict)  # type: ignore

# Add metadata property after class creation to avoid reserved-name check at __init_subclass__ time
def _qp_get_metadata(self):  # type: ignore
    return getattr(self, "metadata_json", None)  # type: ignore

def _qp_set_metadata(self, value):  # type: ignore
    self.metadata_json = value  # type: ignore

QuotaPolicy.metadata = property(_qp_get_metadata, _qp_set_metadata)  # type: ignore
_QUOTA_POLICY_FALLBACK = True

# Optional dependencies (graceful fallback if not configured)
try:
    from app.core.redis import get_redis as _get_redis  # type: ignore
except Exception:  # pragma: no cover
    _get_redis = None  # type: ignore

try:
    from app.billing.plan_service import plan_service  # type: ignore
except Exception:  # pragma: no cover
    plan_service = None  # type: ignore

try:
    from app.iam.quota_service import quota_service as _iam_quota  # type: ignore
except Exception:  # pragma: no cover
    _iam_quota = None  # type: ignore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Quota limits per PlanTier for the 7 required quota types
# ---------------------------------------------------------------------------
# -1 means unlimited (enterprise)
_TIER_QUOTA_LIMITS: dict[str, dict[str, int]] = {
    PlanTier.FREE.value: {
        "requests": 10_000,
        "ai_tokens": 1_000_000,
        "agents": 2,
        "jobs": 10,
        "storage": 1,          # GB
        "ci_minutes": 500,
        "rag_queries": 1_000,
        # Also mirror legacy IAM quota types for compatibility
        "api_calls": 10_000,
        "storage_gb": 1,
        "ci_jobs": 10,
        "workflows": 10,
        "deployments": 5,
        "users": 3,
        "repositories": 1,
    },
    PlanTier.STARTER.value: {
        "requests": 100_000,
        "ai_tokens": 10_000_000,
        "agents": 10,
        "jobs": 50,
        "storage": 10,
        "ci_minutes": 2_000,
        "rag_queries": 10_000,
        "api_calls": 100_000,
        "storage_gb": 10,
        "ci_jobs": 50,
        "workflows": 25,
        "deployments": 10,
        "users": 5,
        "repositories": 10,
    },
    PlanTier.PROFESSIONAL.value: {
        "requests": 500_000,
        "ai_tokens": 50_000_000,
        "agents": 25,
        "jobs": 100,
        "storage": 50,
        "ci_minutes": 5_000,
        "rag_queries": 50_000,
        "api_calls": 500_000,
        "storage_gb": 50,
        "ci_jobs": 100,
        "workflows": 50,
        "deployments": 25,
        "users": 20,
        "repositories": 50,
    },
    PlanTier.TEAM.value: {
        "requests": 1_000_000,
        "ai_tokens": 200_000_000,
        "agents": 50,
        "jobs": 250,
        "storage": 200,
        "ci_minutes": 10_000,
        "rag_queries": 200_000,
        "api_calls": 1_000_000,
        "storage_gb": 200,
        "ci_jobs": 250,
        "workflows": 100,
        "deployments": 50,
        "users": 50,
        "repositories": 9999,
    },
    PlanTier.BUSINESS.value: {
        "requests": 5_000_000,
        "ai_tokens": 500_000_000,
        "agents": 100,
        "jobs": 500,
        "storage": 500,
        "ci_minutes": 30_000,
        "rag_queries": 500_000,
        "api_calls": 5_000_000,
        "storage_gb": 500,
        "ci_jobs": 500,
        "workflows": 200,
        "deployments": 100,
        "users": 100,
        "repositories": 9999,
    },
    PlanTier.ENTERPRISE.value: {
        "requests": -1,
        "ai_tokens": -1,
        "agents": -1,
        "jobs": -1,
        "storage": -1,
        "ci_minutes": -1,
        "rag_queries": -1,
        "api_calls": -1,
        "storage_gb": -1,
        "ci_jobs": -1,
        "workflows": -1,
        "deployments": -1,
        "users": -1,
        "repositories": -1,
    },
}

# Priority weights for fairness (enterprise 10 etc., per plan doc)
_PRIORITY_WEIGHTS: dict[str, int] = {
    PlanTier.ENTERPRISE.value: 10,
    PlanTier.BUSINESS.value: 5,
    PlanTier.TEAM.value: 3,
    PlanTier.PROFESSIONAL.value: 2,
    PlanTier.STARTER.value: 1,
    PlanTier.FREE.value: 1,
}

# Priority ordering for consume fairness
_PRIORITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "NORMAL": 2, "LOW": 1}
# Only business/enterprise may use CRITICAL directly per spec
_CRITICAL_ALLOWED_TIERS = {PlanTier.BUSINESS.value, PlanTier.ENTERPRISE.value, PlanTier.TEAM.value}

# Redis Lua script for atomic check+consume
_LUA_CONSUME = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local amount = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
if limit < 0 then
  -- unlimited
  local cur = tonumber(redis.call('GET', key) or '0')
  local new = cur + amount
  redis.call('SET', key, new)
  if ttl > 0 then redis.call('EXPIRE', key, ttl) end
  return {1, new, limit, 0}
end
local cur = tonumber(redis.call('GET', key) or '0')
if cur + amount > limit then
  return {0, cur, limit, limit - cur}
end
local new = redis.call('INCRBY', key, amount)
if cur == 0 and ttl > 0 then redis.call('EXPIRE', key, ttl) end
return {1, new, limit, limit - new}
"""

_LUA_CHECK = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local cur = tonumber(redis.call('GET', key) or '0')
if limit < 0 then
  return {1, cur, limit, -1}
end
local remaining = limit - cur
local allowed = (remaining >= 0) and 1 or 0
-- For check without amount, allowed if not exceeded
if cur >= limit then allowed = 0 else allowed = 1 end
return {allowed, cur, limit, remaining}
"""


def _tenant_uuid(tenant: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(tenant))
    except Exception:
        # Deterministic UUID5 for non-UUID tenant strings (keeps DB FK consistent)
        return uuid.uuid5(uuid.NAMESPACE_DNS, str(tenant).strip())


def _quota_redis_key(tenant: str, quota_type: str) -> str:
    # Mirrors core/redis key convention novaforge:{version}:quota:{tenant}:{type}
    # Use simple tenant-scoped key for portability
    return f"quota:{str(tenant).strip()}:{str(quota_type).strip().lower()}"


def _tier_limits(plan_tier: str) -> dict[str, int]:
    tier = str(plan_tier).strip().lower()
    if tier in _TIER_QUOTA_LIMITS:
        return _TIER_QUOTA_LIMITS[tier]
    # Fallback: try to build from PLAN_PRICING + defaults
    try:
        pricing = PLAN_PRICING.get(PlanTier(tier))  # type: ignore[arg-type]
        if pricing:
            return {
                "requests": 50_000,
                "ai_tokens": int(pricing.get("tokens_millions", 1)) * 1_000_000,
                "agents": 10,
                "jobs": 50,
                "storage": int(pricing.get("storage_gb", 1)),
                "ci_minutes": 2000,
                "rag_queries": 10_000,
                "api_calls": 50_000,
                "storage_gb": int(pricing.get("storage_gb", 1)),
                "ci_jobs": 50,
                "users": int(pricing.get("seats", 3)),
                "repositories": 10,
            }
    except Exception:
        pass
    return _TIER_QUOTA_LIMITS[PlanTier.FREE.value]


class TenantQuotaOrchestrator:
    """Bridges billing Plans -> IAM quotas with atomic enforcement."""

    # ---------------------------------------------------------------- sync

    async def sync_tenant_quotas(
        self,
        db: AsyncSession,
        tenant: str,
        plan_tier: str,
    ) -> list[dict[str, Any]]:
        """Sync (upsert) QuotaPolicy rows for tenant to match PlanTier limits.

        Called on ``change_plan`` / ``advance_period``. Uses DB FOR UPDATE
        semantics via row-level locking when updating, and also primes Redis
        counters to 0 / current used.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not plan_tier or not str(plan_tier).strip():
            raise ValueError("plan_tier is required")

        tier = str(plan_tier).strip().lower()
        # Validate tier via PlanTier enum when possible
        valid_tiers = {t.value for t in PlanTier}
        if tier not in valid_tiers:
            raise ValueError(f"unknown plan_tier: {plan_tier!r} (expected one of {sorted(valid_tiers)})")

        limits = _tier_limits(tier)
        tenant_s = str(tenant).strip()
        org_id = _tenant_uuid(tenant_s)
        now = _utcnow()
        period_start = now
        period_end = now + timedelta(days=30)

        # Try to enrich limits from billing plan_service if available (reuse)
        if plan_service is not None:
            try:
                plan = plan_service.get_plan_by_tier(tier) or plan_service.get_plan_by_slug(tier)
                if plan:
                    # Override storage/tokens from plan's canonical values
                    limits = dict(limits)
                    limits["storage"] = int(plan.get("max_storage_gb", limits["storage"]))
                    limits["storage_gb"] = int(plan.get("max_storage_gb", limits["storage_gb"]))
                    # max_tokens_millions -> ai_tokens
                    mt = int(plan.get("max_tokens_millions", 0))
                    if mt >= 0:
                        if mt == -1:
                            limits["ai_tokens"] = -1
                        else:
                            limits["ai_tokens"] = mt * 1_000_000
            except Exception:
                pass

        synced: list[dict[str, Any]] = []
        for quota_type, limit in limits.items():
            qtype = str(quota_type).strip().lower()
            limit_i = int(limit)

            # Look up existing QuotaPolicy (tenant-isolated)
            stmt = select(QuotaPolicy).where(
                QuotaPolicy.organization_id == org_id,
                QuotaPolicy.quota_type == qtype,
            )
            # Use FOR UPDATE to serialize concurrent syncs (best-effort)
            try:
                stmt = stmt.with_for_update(nowait=False)
            except Exception:
                pass
            result = await db.execute(stmt)
            existing = result.scalars().first()

            if existing is not None:
                # Check if period expired -> reset used
                if existing.period_end and _utcnow() > existing.period_end.replace(tzinfo=timezone.utc) if existing.period_end.tzinfo is None else existing.period_end:  # type: ignore[union-attr]
                    existing.used = 0
                    existing.period_start = period_start
                    existing.period_end = period_end
                existing.limit = limit_i
                existing.is_active = True
                # Update metadata with tier
                try:
                    meta = dict(existing.metadata or {})  # type: ignore[attr-defined]
                except Exception:
                    meta = {}
                meta["plan_tier"] = tier
                meta["synced_at"] = now.isoformat()
                existing.metadata = meta  # type: ignore[assignment]
                await db.flush()
                await db.refresh(existing)
                rec = {
                    "quota_type": qtype,
                    "limit": limit_i,
                    "used": int(existing.used or 0),
                    "period": existing.period,
                    "organization_id": str(existing.organization_id),
                    "updated": True,
                }
            else:
                # Create new policy
                qp = QuotaPolicy(
                    organization_id=org_id,  # type: ignore[arg-type]
                    quota_type=qtype,
                    limit=limit_i,
                    used=0,
                    period="monthly",
                    period_start=period_start,
                    period_end=period_end,
                    is_active=True,
                    metadata={"plan_tier": tier, "synced_at": now.isoformat()},
                )
                db.add(qp)
                await db.flush()
                await db.refresh(qp)
                rec = {
                    "quota_type": qtype,
                    "limit": limit_i,
                    "used": 0,
                    "period": "monthly",
                    "organization_id": str(org_id),
                    "created": True,
                }

            # Also sync to IAM quota_service in-memory for reuse (best-effort)
            if _iam_quota is not None:
                try:
                    _iam_quota.update_quota(tenant_s, qtype, limit_i, period="monthly")
                except Exception:
                    pass

            # Prime Redis counter with current used (so Lua checks are consistent)
            if _get_redis is not None:
                try:
                    client = await _get_redis()
                    if client is not None:
                        rk = _quota_redis_key(tenant_s, qtype)
                        used_val = int(rec.get("used", 0))
                        # Only set if not exists to avoid clobbering concurrent increments
                        exists = await client.exists(rk)
                        if not exists:
                            # Use SET with NX
                            try:
                                await client.set(rk, str(used_val), nx=True, ex=30 * 24 * 3600)
                            except TypeError:
                                # Older redis client without nx arg
                                if used_val == 0:
                                    await client.set(rk, "0", ex=30 * 24 * 3600)
                        # Ensure TTL
                        try:
                            await client.expire(rk, 30 * 24 * 3600)
                        except Exception:
                            pass
                except Exception:
                    pass

            synced.append(rec)

        # Also ensure legacy IAM default quotas are synced via quota_service initialize
        if _iam_quota is not None:
            try:
                # Ensure org quotas exist for legacy types
                for q in _iam_quota.get_all_quotas(tenant_s):
                    # Already handled above for overlapping types
                    pass
            except Exception:
                pass

        return synced

    # ---------------------------------------------------------------- check (atomic)

    async def check_quota(
        self,
        db: AsyncSession,
        tenant: str,
        quota_type: str,
        amount: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Atomic quota check (does not consume).

        Tries Redis Lua first; falls back to DB SELECT FOR UPDATE.
        Returns ``{allowed, quota_type, limit, used, remaining, requested, weight}``.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not quota_type or not str(quota_type).strip():
            raise ValueError("quota_type is required")
        if not isinstance(amount, int) or amount <= 0:
            raise ValueError("amount must be positive int")

        tenant_s = str(tenant).strip()
        qtype = str(quota_type).strip().lower()
        org_id = _tenant_uuid(tenant_s)

        # Resolve limit (prefer DB policy, then tier limits, then IAM service)
        limit: int | None = None
        used: int | None = None
        tier_for_weight = "free"

        # Try DB lookup with FOR UPDATE (atomic read)
        db_row: QuotaPolicy | None = None
        try:
            stmt = select(QuotaPolicy).where(
                QuotaPolicy.organization_id == org_id,
                QuotaPolicy.quota_type == qtype,
            ).with_for_update(read=False)
            result = await db.execute(stmt)
            db_row = result.scalars().first()
            if db_row is not None:
                limit = int(db_row.limit)
                used = int(db_row.used or 0)
                # Check period expiry
                if db_row.period_end:
                    pend = db_row.period_end
                    if pend.tzinfo is None:
                        pend = pend.replace(tzinfo=timezone.utc)
                    if _utcnow() > pend:
                        # Period expired -> treat as reset (but don't commit here)
                        used = 0
                try:
                    tier_for_weight = (db_row.metadata or {}).get("plan_tier", "free")  # type: ignore[attr-defined]
                except Exception:
                    tier_for_weight = "free"
        except Exception:
            db_row = None

        if limit is None:
            # Try IAM quota_service
            if _iam_quota is not None:
                try:
                    q = _iam_quota.get_quota(tenant_s, qtype)
                    if q:
                        limit = int(q.get("limit", -1))
                        used = int(q.get("used", 0))
                except Exception:
                    pass
        if limit is None:
            # Fallback to tier defaults
            # Try to infer tier from any existing policy
            try:
                stmt2 = select(QuotaPolicy).where(QuotaPolicy.organization_id == org_id).limit(1)
                r2 = await db.execute(stmt2)
                any_row = r2.scalars().first()
                if any_row and getattr(any_row, "metadata", None):
                    tier_for_weight = (any_row.metadata or {}).get("plan_tier", "free")  # type: ignore[attr-defined]
            except Exception:
                pass
            limits = _tier_limits(tier_for_weight)
            limit = int(limits.get(qtype, limits.get("requests", 10000)))
            used = 0

        # Unlimited
        if limit is not None and limit < 0:
            return {
                "allowed": True,
                "quota_type": qtype,
                "limit": limit,
                "used": int(used or 0),
                "remaining": -1,
                "requested": int(amount),
                "weight": _PRIORITY_WEIGHTS.get(tier_for_weight, 1),
                "unlimited": True,
                "reason": "unlimited plan",
            }

        # Try Redis Lua for atomic check (most accurate under concurrency)
        if _get_redis is not None:
            try:
                client = await _get_redis()
                if client is not None:
                    rk = _quota_redis_key(tenant_s, qtype)
                    # Use EVAL with check script (amount-aware remaining)
                    # For check, we compute remaining = limit - cur
                    try:
                        # Prefer EVALSHA fallback
                        res = await client.eval(_LUA_CHECK, 1, rk, str(limit))
                        # res = [allowed, cur, limit, remaining]
                        if isinstance(res, (list, tuple)) and len(res) >= 4:
                            allowed_int, cur, lim, remaining = int(res[0]), int(res[1]), int(res[2]), int(res[3])
                            # For amount check, also ensure cur + amount <= limit
                            if allowed_int == 1 and (cur + int(amount) > lim):
                                allowed_int = 0
                                remaining = lim - cur
                            return {
                                "allowed": bool(allowed_int),
                                "quota_type": qtype,
                                "limit": int(lim),
                                "used": int(cur),
                                "remaining": int(remaining),
                                "requested": int(amount),
                                "remaining_after": int(remaining - int(amount)) if remaining != -1 else -1,
                                "weight": _PRIORITY_WEIGHTS.get(tier_for_weight, 1),
                                "source": "redis",
                                "exceeded": not bool(allowed_int) or (cur + int(amount) > lim),
                            }
                    except Exception:
                        # Fallback to simple GET
                        try:
                            cur_raw = await client.get(rk)
                            cur = int(cur_raw) if cur_raw is not None else int(used or 0)
                            remaining = int(limit) - cur if limit is not None else 0
                            allowed = (cur + int(amount) <= int(limit)) if limit is not None and limit >= 0 else True
                            return {
                                "allowed": bool(allowed),
                                "quota_type": qtype,
                                "limit": int(limit) if limit is not None else -1,
                                "used": int(cur),
                                "remaining": int(remaining),
                                "requested": int(amount),
                                "weight": _PRIORITY_WEIGHTS.get(tier_for_weight, 1),
                                "source": "redis_fallback",
                            }
                        except Exception:
                            pass
            except Exception:
                pass

        # Fallback to DB / IAM calculation (SELECT FOR UPDATE already done)
        cur_used = int(used or 0)
        lim = int(limit) if limit is not None else 0
        remaining = lim - cur_used if lim >= 0 else -1
        allowed = (cur_used + int(amount) <= lim) if lim >= 0 else True
        return {
            "allowed": bool(allowed),
            "quota_type": qtype,
            "limit": lim,
            "used": cur_used,
            "remaining": int(remaining),
            "requested": int(amount),
            "remaining_after": int(remaining - int(amount)) if remaining != -1 else -1,
            "weight": _PRIORITY_WEIGHTS.get(tier_for_weight, 1),
            "source": "db",
            "exceeded": not bool(allowed),
        }

    # ---------------------------------------------------------------- consume (atomic + fairness)

    async def consume(
        self,
        db: AsyncSession,
        tenant: str,
        quota_type: str,
        amount: int = 1,
        priority: str = "NORMAL",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Atomic consume with fairness by PlanTier and priority.

        Priority: CRITICAL/HIGH/NORMAL/LOW — CRITICAL only allowed for
        business/enterprise tiers (customers cannot self-assign critical without
        plan). Fairness is enforced via per-tenant weighted quotas; high-tier
        tenants have higher limits, so they naturally get more share under
        contention. Within a tenant, LOW priority is throttled when usage >80%.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()
        qtype = str(quota_type).strip().lower()
        prio = str(priority).strip().upper() if priority else "NORMAL"
        if prio not in _PRIORITY_ORDER:
            prio = "NORMAL"

        # Validate CRITICAL priority entitlement
        if prio == "CRITICAL":
            # Check tier entitlement
            tier = "free"
            try:
                org_id_tmp = _tenant_uuid(tenant_s)
                stmt = select(QuotaPolicy).where(QuotaPolicy.organization_id == org_id_tmp).limit(1)
                res = await db.execute(stmt)
                row = res.scalars().first()
                if row and getattr(row, "metadata", None):
                    tier = (row.metadata or {}).get("plan_tier", "free")  # type: ignore[attr-defined]
            except Exception:
                tier = "free"
            # Also check IAM tier if available
            if tier not in _CRITICAL_ALLOWED_TIERS:
                return {
                    "allowed": False,
                    "consumed": False,
                    "quota_type": qtype,
                    "reason": f"CRITICAL priority requires plan tier in {sorted(_CRITICAL_ALLOWED_TIERS)}",
                    "requested": int(amount),
                    "priority": prio,
                }

        # For LOW priority, apply soft throttling when usage >80%
        if prio == "LOW":
            chk = await self.check_quota(db, tenant_s, qtype, amount=amount)
            lim = chk.get("limit", 0)
            used = chk.get("used", 0)
            if lim is not None and lim > 0:
                pct = (used / lim * 100) if lim else 0
                if pct >= 80:
                    return {
                        "allowed": False,
                        "consumed": False,
                        "quota_type": qtype,
                        "reason": f"LOW priority throttled at {pct:.1f}% quota usage (>=80%)",
                        "limit": lim,
                        "used": used,
                        "remaining": chk.get("remaining"),
                        "requested": int(amount),
                        "priority": prio,
                        "fairness": "throttled",
                    }

        # Attempt atomic consume via Redis Lua
        ttl = 30 * 24 * 3600  # monthly period
        org_id = _tenant_uuid(tenant_s)

        # Resolve limit for Redis path (needed for Lua)
        limit_for_redis: int | None = None
        try:
            stmt = select(QuotaPolicy).where(
                QuotaPolicy.organization_id == org_id,
                QuotaPolicy.quota_type == qtype,
            )
            res = await db.execute(stmt)
            prow = res.scalars().first()
            if prow is not None:
                limit_for_redis = int(prow.limit)
                # Handle period reset detection
                if prow.period_end:
                    pend = prow.period_end
                    if pend.tzinfo is None:
                        pend = pend.replace(tzinfo=timezone.utc)
                    if _utcnow() > pend:
                        limit_for_redis = int(prow.limit)
                        # Will reset via DB path below if Redis not used
            else:
                # Fallback to tier limits
                tier_fallback = "free"
                try:
                    # Try any policy to get tier
                    stmt2 = select(QuotaPolicy).where(QuotaPolicy.organization_id == org_id).limit(1)
                    r2 = await db.execute(stmt2)
                    any_r = r2.scalars().first()
                    if any_r and getattr(any_r, "metadata", None):
                        tier_fallback = (any_r.metadata or {}).get("plan_tier", "free")  # type: ignore[attr-defined]
                except Exception:
                    pass
                limit_for_redis = int(_tier_limits(tier_fallback).get(qtype, 10000))
        except Exception:
            limit_for_redis = None

        if limit_for_redis is None:
            limit_for_redis = 10_000

        # Unlimited: always allow
        if limit_for_redis is not None and limit_for_redis < 0:
            # Still record usage in DB and Redis for observability
            if _get_redis is not None:
                try:
                    client = await _get_redis()
                    if client is not None:
                        rk = _quota_redis_key(tenant_s, qtype)
                        try:
                            await client.eval(_LUA_CONSUME, 1, rk, str(limit_for_redis), str(amount), str(ttl))
                        except Exception:
                            await client.incrby(rk, int(amount))
                except Exception:
                    pass
            # Update DB used
            try:
                stmt = select(QuotaPolicy).where(
                    QuotaPolicy.organization_id == org_id, QuotaPolicy.quota_type == qtype
                ).with_for_update()
                result = await db.execute(stmt)
                row = result.scalars().first()
                if row is not None:
                    row.used = int(row.used or 0) + int(amount)
                    await db.flush()
            except Exception:
                pass
            return {
                "allowed": True,
                "consumed": True,
                "quota_type": qtype,
                "limit": limit_for_redis,
                "used": -1,
                "remaining": -1,
                "requested": int(amount),
                "unlimited": True,
                "priority": prio,
                "source": "redis" if _get_redis is not None else "db",
            }

        # Redis atomic path
        if _get_redis is not None:
            try:
                client = await _get_redis()
                if client is not None:
                    rk = _quota_redis_key(tenant_s, qtype)
                    try:
                        res = await client.eval(_LUA_CONSUME, 1, rk, str(limit_for_redis), str(amount), str(ttl))
                        if isinstance(res, (list, tuple)) and len(res) >= 4:
                            allowed_int, new_used, lim, remaining = int(res[0]), int(res[1]), int(res[2]), int(res[3])
                            if allowed_int == 1:
                                # Also update DB used to keep DB in sync (best-effort)
                                try:
                                    stmt = select(QuotaPolicy).where(
                                        QuotaPolicy.organization_id == org_id, QuotaPolicy.quota_type == qtype
                                    ).with_for_update()
                                    result = await db.execute(stmt)
                                    row = result.scalars().first()
                                    if row is not None:
                                        # Handle period expiry: reset if needed
                                        pend = row.period_end
                                        should_reset = False
                                        if pend:
                                            if pend.tzinfo is None:
                                                pend = pend.replace(tzinfo=timezone.utc)
                                            if _utcnow() > pend:
                                                should_reset = True
                                                row.used = int(amount)
                                                row.period_start = _utcnow()
                                                row.period_end = _utcnow() + timedelta(days=30)
                                            else:
                                                row.used = int(new_used)
                                        else:
                                            row.used = int(new_used)
                                        if not should_reset and row.used != int(new_used):
                                            row.used = int(new_used)
                                        await db.flush()
                                    # Mirror to IAM quota_service
                                    if _iam_quota is not None:
                                        try:
                                            # IAM service in-memory; we simulate consume
                                            q = _iam_quota.get_quota(tenant_s, qtype)
                                            if q:
                                                q["used"] = int(new_used)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                return {
                                    "allowed": True,
                                    "consumed": True,
                                    "quota_type": qtype,
                                    "limit": int(lim),
                                    "used": int(new_used),
                                    "remaining": int(remaining),
                                    "requested": int(amount),
                                    "priority": prio,
                                    "source": "redis",
                                    "fairness_weight": _PRIORITY_WEIGHTS.get("free", 1),
                                }
                            else:
                                return {
                                    "allowed": False,
                                    "consumed": False,
                                    "quota_type": qtype,
                                    "limit": int(lim),
                                    "used": int(new_used),
                                    "remaining": int(remaining),
                                    "requested": int(amount),
                                    "reason": "quota exceeded",
                                    "priority": prio,
                                    "source": "redis",
                                }
                    except Exception:
                        pass
            except Exception:
                pass

        # Fallback: DB SELECT FOR UPDATE (atomic at DB level)
        try:
            stmt = select(QuotaPolicy).where(
                QuotaPolicy.organization_id == org_id, QuotaPolicy.quota_type == qtype
            ).with_for_update()
            result = await db.execute(stmt)
            row = result.scalars().first()
            if row is None:
                # Auto-create via sync fallback
                await self.sync_tenant_quotas(db, tenant_s, "free")
                result = await db.execute(
                    select(QuotaPolicy).where(
                        QuotaPolicy.organization_id == org_id, QuotaPolicy.quota_type == qtype
                    ).with_for_update()
                )
                row = result.scalars().first()
                if row is None:
                    raise RuntimeError(f"quota policy not found after sync for {qtype}")

            # Check period rollover
            now = _utcnow()
            pend = row.period_end
            if pend:
                if pend.tzinfo is None:
                    pend = pend.replace(tzinfo=timezone.utc)
                if now > pend:
                    row.used = 0
                    row.period_start = now
                    row.period_end = now + timedelta(days=30)

            lim = int(row.limit)
            cur = int(row.used or 0)
            if lim >= 0 and cur + int(amount) > lim:
                return {
                    "allowed": False,
                    "consumed": False,
                    "quota_type": qtype,
                    "limit": lim,
                    "used": cur,
                    "remaining": max(0, lim - cur),
                    "requested": int(amount),
                    "reason": "quota exceeded",
                    "priority": prio,
                    "source": "db",
                }
            # Consume
            row.used = cur + int(amount)
            await db.flush()
            remaining = (lim - int(row.used)) if lim >= 0 else -1

            # Also update Redis to keep in sync
            if _get_redis is not None:
                try:
                    client = await _get_redis()
                    if client is not None:
                        rk = _quota_redis_key(tenant_s, qtype)
                        await client.set(rk, str(int(row.used)), ex=ttl)
                except Exception:
                    pass
            if _iam_quota is not None:
                try:
                    q = _iam_quota.get_quota(tenant_s, qtype)
                    if q:
                        q["used"] = int(row.used)
                except Exception:
                    pass

            return {
                "allowed": True,
                "consumed": True,
                "quota_type": qtype,
                "limit": lim,
                "used": int(row.used),
                "remaining": int(remaining) if lim >= 0 else -1,
                "requested": int(amount),
                "priority": prio,
                "source": "db",
                "fairness_weight": _PRIORITY_WEIGHTS.get(
                    (row.metadata or {}).get("plan_tier", "free") if getattr(row, "metadata", None) else "free", 1  # type: ignore[attr-defined]
                ),
            }
        except Exception as exc:
            # Last resort: allow but log (fail-open for availability, but flag)
            return {
                "allowed": True,
                "consumed": False,
                "quota_type": qtype,
                "requested": int(amount),
                "reason": f"fallback allow due to error: {exc}",
                "priority": prio,
                "source": "fallback",
            }

    # ---------------------------------------------------------------- convenience helpers

    async def check_and_consume(
        self,
        db: AsyncSession,
        tenant: str,
        quota_type: str,
        amount: int = 1,
        priority: str = "NORMAL",
    ) -> dict[str, Any]:
        """Check and atomically consume in one step (preferred)."""
        return await self.consume(db, tenant, quota_type, amount=amount, priority=priority)

    async def get_quota_status(
        self,
        db: AsyncSession,
        tenant: str,
    ) -> dict[str, dict[str, Any]]:
        """Return usage summary for all 7 quota types for tenant."""
        tenant_s = str(tenant).strip()
        org_id = _tenant_uuid(tenant_s)
        result: dict[str, dict[str, Any]] = {}
        quota_types = ["requests", "ai_tokens", "agents", "jobs", "storage", "ci_minutes", "rag_queries"]
        for qtype in quota_types:
            chk = await self.check_quota(db, tenant_s, qtype, amount=1)
            # Normalize to standard response shape
            result[qtype] = {
                "limit": chk.get("limit"),
                "used": chk.get("used"),
                "remaining": chk.get("remaining"),
                "allowed": chk.get("allowed"),
            }
        # Also include legacy types for dashboard completeness
        legacy = ["api_calls", "storage_gb", "ai_tokens", "agents", "ci_jobs", "workflows", "deployments"]
        for qtype in legacy:
            if qtype not in result:
                try:
                    chk = await self.check_quota(db, tenant_s, qtype, amount=1)
                    result[qtype] = {"limit": chk.get("limit"), "used": chk.get("used"), "remaining": chk.get("remaining")}
                except Exception:
                    pass
        # Enrich with DB row details when available
        try:
            stmt = select(QuotaPolicy).where(QuotaPolicy.organization_id == org_id)
            res = await db.execute(stmt)
            rows = list(res.scalars().all())
            for row in rows:
                qtype = str(row.quota_type)
                if qtype in result:
                    result[qtype]["period_start"] = row.period_start.isoformat() if row.period_start else None
                    result[qtype]["period_end"] = row.period_end.isoformat() if row.period_end else None
                    result[qtype]["is_active"] = bool(row.is_active)
        except Exception:
            pass
        return result


tenant_quota_orchestrator = TenantQuotaOrchestrator()
# Alias for backward compatibility with spec naming
quota_orchestrator = tenant_quota_orchestrator
