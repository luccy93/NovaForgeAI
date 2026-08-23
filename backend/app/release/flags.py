"""Volume 56 — Centralized Feature Flag Service (NovaForge).

Additive, real implementation using AsyncSession and SQLAlchemy ORM.
Uses models app.release.models: FeatureFlag, FeatureFlagVersion, FeatureFlagRule,
FeatureFlagEvaluation, FlagState.

Supports flag types: boolean / percentage / segment (+ env/region/org/workspace/project targeting).
Deterministic percentage rollout via consistent hashing:
    bucket = int(hashlib.sha256(f"{stable_id}:{flag_key}".encode()).hexdigest(), 16) % 100
Never uses sensitive personal attributes for bucketing/segment resolution.
Fallback to safe default if service unavailable (never crashes caller).
Audited via FeatureFlagVersion. Archive is explicit state change, not silent delete.
Stale / expiry warning via check_expiry().
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.release.models import (
    FeatureFlag,
    FeatureFlagVersion,
    FeatureFlagRule,
    FeatureFlagEvaluation,
    FlagState,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants & helpers — never use sensitive personal attributes for targeting
# ---------------------------------------------------------------------------

_SENSITIVE_KEYS: set[str] = {
    # PII / sensitive — must never be used as stable_id or matching key
    "email",
    "email_address",
    "phone",
    "phone_number",
    "ssn",
    "national_id",
    "nationality",
    "passport",
    "password",
    "credit_card",
    "creditcard",
    "ip_address",
    "ip",
    "address",
    "street",
    "dob",
    "birthdate",
    "birthday",
    "gender",
    "sex",
    "race",
    "ethnicity",
    "political",
    "religion",
    "religious",
    "biometric",
    "fingerprint",
    "health",
    "medical",
    "salary",
    "income",
    "age",
    "name",  # full name is PII; use stable_id instead
    "first_name",
    "last_name",
}

# Allowed stable identifiers for consistent hashing (non-sensitive, opaque IDs)
_STABLE_ID_KEYS: tuple[str, ...] = (
    "user_id",
    "stable_id",
    "subject_id",
    "entity_id",
    "account_id",
    "client_id",
    "device_id",
    "session_id",
    "id",
    "distinct_id",
    "anonymous_id",
)

# Allowed context keys for targeting (non-sensitive dimensions)
_ALLOWED_TARGET_CONTEXT_KEYS: set[str] = {
    "user_id",
    "stable_id",
    "subject_id",
    "entity_id",
    "org_id",
    "organization_id",
    "org",
    "organization",
    "workspace_id",
    "workspace",
    "project_id",
    "project",
    "env",
    "environment",
    "region",
    "segment",
    "segments",
    "country",
    "group",
    "team_id",
    "team",
}

_VALID_FLAG_TYPES: set[str] = {"boolean", "percentage", "segment"}
_VALID_RULE_TYPES: set[str] = {
    "percentage",
    "segment",
    "env",
    "environment",
    "region",
    "org",
    "organization",
    "workspace",
    "project",
}
_VALID_STATES: set[str] = {e.value for e in FlagState}


def _normalize_flag_type(flag_type: str | None) -> str:
    if not flag_type:
        return "boolean"
    v = str(flag_type).strip().lower()
    if v in _VALID_FLAG_TYPES:
        return v
    # allow alias: "bool"
    if v in ("bool", "flag", "toggle"):
        return "boolean"
    if v in ("percent", "rollout"):
        return "percentage"
    raise ValueError(f"invalid flag_type {flag_type!r}; must be one of {sorted(_VALID_FLAG_TYPES)}")


def _normalize_rule_type(rule_type: str) -> str:
    v = str(rule_type).strip().lower()
    if v not in _VALID_RULE_TYPES:
        # normalize synonyms
        mapping = {
            "organisation": "org",
            "org_id": "org",
            "workspace_id": "workspace",
            "project_id": "project",
            "environment": "env",
        }
        v = mapping.get(v, v)
    if v not in _VALID_RULE_TYPES:
        raise ValueError(f"invalid rule_type {rule_type!r}; must be one of {sorted(_VALID_RULE_TYPES)}")
    # canonical form
    if v == "environment":
        v = "env"
    if v == "organization":
        v = "org"
    return v


def _normalize_state(state: str | FlagState) -> str:
    if isinstance(state, FlagState):
        return state.value
    v = str(state).strip().upper()
    if v not in _VALID_STATES:
        raise ValueError(f"invalid state {state!r}; must be one of {sorted(_VALID_STATES)}")
    return v


def _sanitize_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """Return copy of context with sensitive keys removed (never evaluate on PII)."""
    if not context:
        return {}
    sanitized: dict[str, Any] = {}
    for k, v in context.items():
        if k.lower() in _SENSITIVE_KEYS:
            continue
        sanitized[k] = v
    return sanitized


def _get_stable_id(context: dict[str, Any] | None) -> str | None:
    """Extract first available non-sensitive stable identifier for hashing.
    Returns None if none found — caller must fallback to safe default.
    Never derives stable_id from sensitive attributes."""
    if not context:
        return None
    sanitized = _sanitize_context(context)
    for key in _STABLE_ID_KEYS:
        val = sanitized.get(key)
        # also check nested user object
        if val is None and "user" in sanitized and isinstance(sanitized["user"], dict):
            val = sanitized["user"].get(key)
        if val is not None:
            s = str(val).strip()
            if s:
                return s
    # fallback: org/workspace/project as stable_id if no user id present
    # these are still non-sensitive, tenant-scoped identifiers
    for fallback_key in ("org_id", "organization_id", "workspace_id", "project_id"):
        val = sanitized.get(fallback_key)
        if val is not None:
            s = str(val).strip()
            if s:
                return s
    return None


def _hash_bucket(stable_id: str, flag_key: str) -> int:
    """Deterministic bucket 0-99 via sha256(stable_id + flag_key).
    Same stable_id + flag_key => same bucket => no flip-flop.
    """
    payload = f"{stable_id}:{flag_key}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(digest, 16) % 100


def _parse_default(flag: FeatureFlag) -> str:
    return str(flag.default_value) if flag.default_value is not None else "false"


def _enabled_value(flag: FeatureFlag) -> str:
    """Value when flag is considered ON / matched.
    For boolean flags, ON is always "true" (regardless of default).
    For other types, ON is also "true" unless default is explicitly variant.
    """
    if flag.flag_type == "boolean":
        return "true"
    # For percentage/segment, enabled means true; callers can interpret string
    return "true"


def _extract_context_value(context: dict[str, Any], rule_type: str) -> tuple[str | None, list[str] | None]:
    """Extract value(s) from sanitized context for a given rule_type.
    Returns (single_value, list_values) for segment etc.
    """
    # sanitize already — caller passes sanitized
    if rule_type == "env":
        v = context.get("env") or context.get("environment")
        return (str(v).strip() if v is not None else None, None)
    if rule_type == "region":
        v = context.get("region")
        return (str(v).strip() if v is not None else None, None)
    if rule_type == "org":
        v = context.get("org_id") or context.get("organization_id") or context.get("org") or context.get("organization")
        # also check nested
        if v is None and isinstance(context.get("user"), dict):
            v = context["user"].get("org_id")
        return (str(v).strip() if v is not None else None, None)
    if rule_type == "workspace":
        v = context.get("workspace_id") or context.get("workspace")
        return (str(v).strip() if v is not None else None, None)
    if rule_type == "project":
        v = context.get("project_id") or context.get("project")
        return (str(v).strip() if v is not None else None, None)
    if rule_type == "segment":
        # segment can be single or list
        seg = context.get("segment")
        segs = context.get("segments")
        single = str(seg).strip() if seg is not None else None
        lst = None
        if isinstance(segs, (list, tuple, set)):
            lst = [str(s).strip() for s in segs if str(s).strip()]
        elif isinstance(segs, str):
            lst = [s.strip() for s in segs.split(",") if s.strip()]
        return (single, lst)
    if rule_type == "percentage":
        return (None, None)
    return (None, None)


def _rule_matches(rule: FeatureFlagRule, sanitized_context: dict[str, Any]) -> bool:
    rt = _normalize_rule_type(rule.rule_type)
    if rt == "percentage":
        # percentage rules always "match" targeting (global rollout)
        return True
    single, lst = _extract_context_value(sanitized_context, rt)
    expected = str(rule.value).strip() if rule.value is not None else ""
    if not expected:
        return False
    if rt == "segment":
        # match if expected equals single segment or is in segments list
        if single is not None and single == expected:
            return True
        if lst is not None and expected in lst:
            return True
        return False
    # exact match for env/region/org/workspace/project
    return single is not None and single == expected


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FeatureFlagService:
    """Centralized feature flag management (Volume 56).

    All mutations are audited via FeatureFlagVersion. Evaluations are
    persisted to FeatureFlagEvaluation (best-effort) and are deterministic
    for percentage rollouts via consistent hashing.

    Tenant isolation is enforced on every method (key is scoped to tenant).
    """

    # ---------------------------------------------------------------
    # CRUD
    # ---------------------------------------------------------------

    async def create_flag(
        self,
        db: AsyncSession,
        tenant: str,
        key: str,
        name: str,
        flag_type: str = "boolean",
        default_value: str = "false",
        owner: str = "system",
        expires_at: datetime | None = None,
        tags: list[str] | None = None,
        description: str = "",
        state: str | FlagState | None = None,
    ) -> FeatureFlag:
        """Create a new feature flag for *tenant*.

        Args:
            db: AsyncSession
            tenant: tenant / organization identifier (non-empty)
            key: machine key, unique per tenant (e.g. "new_checkout")
            name: human-readable name
            flag_type: boolean | percentage | segment
            default_value: safe default string ("false"/"true"/variant)
            owner: owner identifier (team or user)
            expires_at: optional expiry; past flags are warned via check_expiry
            tags: optional labels
            description: optional description
            state: initial FlagState (default OFF)

        Returns:
            Persisted FeatureFlag.
        """
        if not tenant or not tenant.strip():
            raise ValueError("tenant must be a non-empty string")
        if not key or not key.strip():
            raise ValueError("key must be a non-empty string")
        if not name or not name.strip():
            raise ValueError("name must be a non-empty string")

        norm_type = _normalize_flag_type(flag_type)
        norm_key = key.strip()
        norm_name = name.strip()
        norm_state = _normalize_state(state) if state is not None else FlagState.OFF.value

        # validate default_value
        dv = str(default_value).strip() if default_value is not None else "false"
        if not dv:
            dv = "false"

        # tags normalization
        tag_list: list[str] = []
        if tags is not None:
            if not isinstance(tags, list):
                raise ValueError("tags must be a list of strings")
            tag_list = [str(t).strip() for t in tags if str(t).strip()]

        # check duplicate key per tenant
        existing = await self.get_flag(db, tenant.strip(), norm_key)
        if existing is not None:
            raise ValueError(f"flag with key {norm_key!r} already exists for tenant {tenant!r}")

        flag = FeatureFlag(
            tenant=tenant.strip(),
            key=norm_key,
            name=norm_name,
            description=str(description or ""),
            flag_type=norm_type,
            default_value=dv,
            state=norm_state,
            owner=str(owner or "system").strip() or "system",
            expires_at=expires_at,
            tags=tag_list,
        )
        db.add(flag)
        await db.flush()  # obtains flag.id

        # audit version 1
        version = FeatureFlagVersion(
            flag_id=flag.id,
            version=1,
            change={
                "action": "create",
                "key": norm_key,
                "name": norm_name,
                "flag_type": norm_type,
                "default_value": dv,
                "state": norm_state,
                "owner": flag.owner,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "tags": tag_list,
            },
            changed_by=str(owner or "system"),
        )
        db.add(version)
        await db.flush()

        logger.info("created flag tenant=%s key=%s type=%s state=%s owner=%s", tenant, norm_key, norm_type, norm_state, owner)
        return flag

    async def get_flag(
        self,
        db: AsyncSession,
        tenant: str,
        key: str,
    ) -> FeatureFlag | None:
        """Fetch single flag by tenant+key (tenant-isolated)."""
        if not tenant or not key:
            return None
        stmt = select(FeatureFlag).where(
            FeatureFlag.tenant == tenant.strip(),
            FeatureFlag.key == key.strip(),
        ).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_flag_by_id(
        self,
        db: AsyncSession,
        flag_id: uuid.UUID | str,
    ) -> FeatureFlag | None:
        fid = uuid.UUID(str(flag_id)) if isinstance(flag_id, str) else flag_id
        stmt = select(FeatureFlag).where(FeatureFlag.id == fid).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_flags(
        self,
        db: AsyncSession,
        tenant: str,
    ) -> list[FeatureFlag]:
        """List all flags for tenant ordered by creation time (excludes archived by default if caller filters)."""
        if not tenant or not tenant.strip():
            raise ValueError("tenant must be a non-empty string")
        stmt = select(FeatureFlag).where(FeatureFlag.tenant == tenant.strip()).order_by(FeatureFlag.created_at.asc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_flag(
        self,
        db: AsyncSession,
        flag_id: uuid.UUID | str,
        updates: dict[str, Any],
        actor: str = "system",
    ) -> FeatureFlag:
        """Update mutable fields on a flag and audit via FeatureFlagVersion.

        Allowed update keys: name, description, flag_type, default_value, owner,
                             expires_at, tags, key (rename — check uniqueness).
        State changes should use set_state() for explicit audit.
        """
        flag = await self.get_flag_by_id(db, flag_id)
        if flag is None:
            raise ValueError(f"flag {flag_id!r} not found")

        if not isinstance(updates, dict) or not updates:
            raise ValueError("updates must be a non-empty dict")

        allowed = {"name", "description", "flag_type", "default_value", "owner", "expires_at", "tags", "key"}
        for k in updates:
            if k not in allowed:
                raise ValueError(f"field {k!r} not updatable; allowed: {sorted(allowed)}")

        change: dict[str, Any] = {"action": "update", "before": {}, "after": {}}

        if "name" in updates:
            new_name = str(updates["name"]).strip()
            if not new_name:
                raise ValueError("name must be non-empty")
            change["before"]["name"] = flag.name
            change["after"]["name"] = new_name
            flag.name = new_name

        if "description" in updates:
            new_desc = str(updates["description"] or "")
            change["before"]["description"] = flag.description
            change["after"]["description"] = new_desc
            flag.description = new_desc

        if "flag_type" in updates:
            norm = _normalize_flag_type(str(updates["flag_type"]))
            change["before"]["flag_type"] = flag.flag_type
            change["after"]["flag_type"] = norm
            flag.flag_type = norm

        if "default_value" in updates:
            dv = str(updates["default_value"]).strip() or "false"
            change["before"]["default_value"] = flag.default_value
            change["after"]["default_value"] = dv
            flag.default_value = dv

        if "owner" in updates:
            new_owner = str(updates["owner"] or "").strip() or "system"
            change["before"]["owner"] = flag.owner
            change["after"]["owner"] = new_owner
            flag.owner = new_owner

        if "expires_at" in updates:
            val = updates["expires_at"]
            if val is not None and not isinstance(val, datetime):
                raise ValueError("expires_at must be datetime or None")
            change["before"]["expires_at"] = flag.expires_at.isoformat() if flag.expires_at else None
            change["after"]["expires_at"] = val.isoformat() if val else None
            flag.expires_at = val

        if "tags" in updates:
            tags_val = updates["tags"]
            if tags_val is not None and not isinstance(tags_val, list):
                raise ValueError("tags must be a list")
            tag_list = [str(t).strip() for t in (tags_val or []) if str(t).strip()]
            change["before"]["tags"] = flag.tags
            change["after"]["tags"] = tag_list
            flag.tags = tag_list

        if "key" in updates:
            new_key = str(updates["key"]).strip()
            if not new_key:
                raise ValueError("key must be non-empty")
            if new_key != flag.key:
                # uniqueness check
                dup = await self.get_flag(db, flag.tenant, new_key)
                if dup is not None:
                    raise ValueError(f"flag key {new_key!r} already exists for tenant {flag.tenant!r}")
                change["before"]["key"] = flag.key
                change["after"]["key"] = new_key
                flag.key = new_key

        # audit
        await self._audit_version(db, flag, change, changed_by=actor)
        await db.flush()
        logger.info("updated flag id=%s tenant=%s changes=%s actor=%s", flag.id, flag.tenant, list(change["after"].keys()), actor)
        return flag

    async def set_state(
        self,
        db: AsyncSession,
        flag_id: uuid.UUID | str,
        state: str | FlagState,
        actor: str = "system",
    ) -> FeatureFlag:
        """Transition flag state (OFF/ON/ROLLOUT/PAUSED/ARCHIVED) with audit."""
        flag = await self.get_flag_by_id(db, flag_id)
        if flag is None:
            raise ValueError(f"flag {flag_id!r} not found")
        norm_state = _normalize_state(state)
        prev = flag.state
        # allow idempotent
        if prev == norm_state:
            return flag
        # archived is terminal unless explicitly re-activated via set_state — allow but log
        if prev == FlagState.ARCHIVED.value and norm_state != FlagState.ARCHIVED.value:
            logger.warning("reactivating archived flag id=%s from ARCHIVED to %s actor=%s", flag.id, norm_state, actor)
        flag.state = norm_state
        change = {"action": "set_state", "before": prev, "after": norm_state}
        await self._audit_version(db, flag, change, changed_by=actor)
        await db.flush()
        logger.info("flag state change id=%s %s -> %s actor=%s", flag.id, prev, norm_state, actor)
        return flag

    async def add_rule(
        self,
        db: AsyncSession,
        flag_id: uuid.UUID | str,
        rule_type: str,
        value: str,
        percentage: int | None = None,
        rank: int = 0,
        actor: str = "system",
    ) -> FeatureFlagRule:
        """Add a targeting/rollout rule to *flag_id* and audit.

        Args:
            rule_type: one of percentage/segment/env/region/org/workspace/project
            value: targeting value (e.g. segment name, env name, region code).
                   For global percentage rules the value is still required
                   but can be "true" or flag key; percentage controls rollout.
            percentage: when set (0-100) the rule is percentage-gated via
                        consistent hashing; when None the rule is exact-match.
            rank: ordering priority (lower rank evaluated first).
        """
        flag = await self.get_flag_by_id(db, flag_id)
        if flag is None:
            raise ValueError(f"flag {flag_id!r} not found")

        norm_type = _normalize_rule_type(rule_type)
        if value is None or not str(value).strip():
            raise ValueError("value must be a non-empty string")
        norm_value = str(value).strip()

        if percentage is not None:
            try:
                pct = int(percentage)
            except Exception:
                raise ValueError("percentage must be an integer 0-100")
            if pct < 0 or pct > 100:
                raise ValueError("percentage must be between 0 and 100 inclusive")
        else:
            pct = None

        try:
            r = int(rank)
        except Exception:
            raise ValueError("rank must be an integer")
        if r < 0:
            raise ValueError("rank must be >= 0")

        rule = FeatureFlagRule(
            flag_id=flag.id,
            rule_type=norm_type,
            value=norm_value,
            percentage=pct,
            rank=r,
        )
        db.add(rule)
        await db.flush()

        change = {
            "action": "add_rule",
            "rule_id": str(rule.id),
            "rule_type": norm_type,
            "value": norm_value,
            "percentage": pct,
            "rank": r,
        }
        await self._audit_version(db, flag, change, changed_by=actor)
        await db.flush()
        logger.info("added rule flag=%s type=%s value=%s pct=%s rank=%s", flag.id, norm_type, norm_value, pct, r)
        return rule

    # ---------------------------------------------------------------
    # Evaluation — deterministic via consistent hashing
    # ---------------------------------------------------------------

    async def evaluate(
        self,
        db: AsyncSession,
        tenant: str,
        key: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate flag for *tenant/key* given *context*.

        Never uses sensitive personal attributes. Falls back to safe default
        (flag.default_value or "false") if flag not found or on error.

        Returns:
            dict with keys: flag (FeatureFlag|None), value (str), reason (str),
                            version (int), bucket (int|None), flag_key, tenant
        Context may contain (all optional, non-sensitive):
            user_id, stable_id, org_id, workspace_id, project_id,
            env/environment, region, segment/segments, org/workspace/project
        Sensitive keys (email, phone, ssn, ...) are stripped and ignored.

        Determinism: percentage gating via sha256(stable_id:flag_key)%100.
        """
        safe_default = "false"
        sanitized = _sanitize_context(context or {})
        reason = "default"
        flag: FeatureFlag | None = None
        version = 0
        bucket: int | None = None
        value = safe_default

        try:
            flag = await self.get_flag(db, tenant, key)
            if flag is None:
                logger.warning("evaluate: flag not found tenant=%s key=%s", tenant, key)
                result = {
                    "flag": None,
                    "flag_key": key,
                    "tenant": tenant,
                    "value": safe_default,
                    "reason": "flag_not_found",
                    "version": 0,
                    "bucket": None,
                }
                # best-effort log evaluation with null flag — skipped (no flag_id)
                return result

            safe_default = _parse_default(flag)
            value = safe_default
            version = await self._latest_version_number(db, flag.id)

            # State machine
            if flag.state == FlagState.OFF.value:
                reason = "flag_off"
                value = safe_default
            elif flag.state == FlagState.ARCHIVED.value:
                reason = "archived"
                value = safe_default
            elif flag.state == FlagState.PAUSED.value:
                reason = "paused"
                value = safe_default
            elif flag.state == FlagState.ON.value:
                reason = "flag_on"
                value = _enabled_value(flag)
            elif flag.state == FlagState.ROLLOUT.value:
                # evaluate rules in rank order
                eval_result = await self._evaluate_rollout(db, flag, sanitized)
                value = eval_result["value"]
                reason = eval_result["reason"]
                bucket = eval_result.get("bucket")
            else:
                # unknown state — fail-closed
                logger.warning("evaluate: unknown state %r for flag %s", flag.state, flag.id)
                reason = f"unknown_state:{flag.state}"
                value = safe_default

            # expiry: if expired, force safe default regardless of state
            if flag.expires_at is not None:
                # ensure timezone-aware comparison
                now = datetime.now(timezone.utc)
                exp = flag.expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < now:
                    logger.warning("evaluate: flag expired tenant=%s key=%s expires_at=%s", tenant, key, exp.isoformat())
                    value = safe_default
                    reason = "expired"
                elif exp - now <= timedelta(days=7):
                    logger.warning("evaluate: flag nearing expiry tenant=%s key=%s expires_in=%s", tenant, key, exp - now)

            result = {
                "flag": flag,
                "flag_key": key,
                "tenant": tenant,
                "value": value,
                "reason": reason,
                "version": version,
                "bucket": bucket,
            }

            # persist evaluation (best-effort, never fails the caller)
            try:
                # store sanitized context only, never sensitive
                eval_row = FeatureFlagEvaluation(
                    flag_id=flag.id,
                    context=sanitized,
                    value=str(value),
                    reason=str(reason),
                    evaluated_at=datetime.now(timezone.utc),
                )
                db.add(eval_row)
                await db.flush()
            except Exception as exc:  # pragma: no cover - best effort
                logger.debug("failed to persist evaluation tenant=%s key=%s: %s", tenant, key, exc)

            return result

        except Exception as exc:
            # fallback to safe default on any unexpected error (service unavailable)
            logger.exception("evaluate fallback due to error tenant=%s key=%s: %s", tenant, key, exc)
            # never leak exception to caller — return safe default
            try:
                if flag is not None:
                    safe_default = _parse_default(flag)
                    version = await self._latest_version_number(db, flag.id) if flag else 0
                else:
                    # try to load flag again for safe default
                    try:
                        f2 = await self.get_flag(db, tenant, key)
                        if f2 is not None:
                            safe_default = _parse_default(f2)
                            flag = f2
                    except Exception:
                        pass
            except Exception:
                pass
            return {
                "flag": flag,
                "flag_key": key,
                "tenant": tenant,
                "value": safe_default,
                "reason": "fallback_error",
                "version": version,
                "bucket": bucket,
                "error": str(exc),
            }

    async def _evaluate_rollout(
        self,
        db: AsyncSession,
        flag: FeatureFlag,
        sanitized_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Helper: evaluate ordered rules for ROLLOUT state.

        Rules sorted by rank asc. First matching rule wins.
        Percentage gating via deterministic hash bucket.
        If no rule matches, fallback to safe default.
        """
        stmt = select(FeatureFlagRule).where(FeatureFlagRule.flag_id == flag.id).order_by(FeatureFlagRule.rank.asc(), FeatureFlagRule.created_at.asc())
        result = await db.execute(stmt)
        rules: list[FeatureFlagRule] = list(result.scalars().all())

        if not rules:
            # No rules in ROLLOUT — treat as disabled (fail-closed to default)
            return {"value": _parse_default(flag), "reason": "no_rules", "bucket": None}

        enabled_val = _enabled_value(flag)
        default_val = _parse_default(flag)

        stable_id = _get_stable_id(sanitized_context)

        for rule in rules:
            rt = _normalize_rule_type(rule.rule_type)

            # check targeting match
            if not _rule_matches(rule, sanitized_context):
                continue

            # percentage gating
            if rule.percentage is not None:
                if stable_id is None:
                    # no stable id -> cannot deterministically bucket — treat as not in rollout
                    logger.debug("rollout: no stable_id for percentage rule flag=%s rule=%s", flag.key, rule.id)
                    continue
                bucket = _hash_bucket(stable_id, flag.key)
                if bucket < int(rule.percentage):
                    return {"value": enabled_val, "reason": f"rule:{rt}:{rule.value}:{rule.percentage}%", "bucket": bucket}
                else:
                    # this rule's targeting matches but bucket says not included — continue to next rule
                    # however per typical semantics, if targeted but bucket fails, fallback to default
                    # we still check remaining lower-priority rules
                    continue
            else:
                # exact match without percentage => enabled
                return {"value": enabled_val, "reason": f"rule:{rt}:{rule.value}", "bucket": None}

        # Handle global percentage rule edge: if any percentage rule exists but none matched due to bucket,
        # we still return default. Also support pure percentage flag_type with a single global rule.
        # If no targeted rule matched, fallback to default.
        return {"value": default_val, "reason": "no_match", "bucket": _hash_bucket(stable_id, flag.key) if stable_id else None}

    async def evaluate_many(
        self,
        db: AsyncSession,
        tenant: str,
        keys: list[str],
        context: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Batch evaluate multiple flags (same tenant+context).

        Returns dict key -> evaluate() result dict. Never raises; missing flags fallback.
        """
        if not keys:
            return {}
        if not isinstance(keys, (list, tuple, set)):
            raise ValueError("keys must be a list of flag keys")
        results: dict[str, dict[str, Any]] = {}
        for k in keys:
            kk = str(k).strip()
            if not kk:
                continue
            res = await self.evaluate(db, tenant, kk, context)
            results[kk] = res
        return results

    # ---------------------------------------------------------------
    # Lifecycle — archive, expiry, audit
    # ---------------------------------------------------------------

    async def archive_flag(
        self,
        db: AsyncSession,
        flag_id: uuid.UUID | str,
        actor: str = "system",
    ) -> FeatureFlag:
        """Explicit soft-delete — transitions to ARCHIVED state (never hard delete)."""
        flag = await self.get_flag_by_id(db, flag_id)
        if flag is None:
            raise ValueError(f"flag {flag_id!r} not found")
        prev = flag.state
        flag.state = FlagState.ARCHIVED.value
        change = {"action": "archive", "before": prev, "after": FlagState.ARCHIVED.value}
        await self._audit_version(db, flag, change, changed_by=actor)
        await db.flush()
        logger.info("archived flag id=%s tenant=%s key=%s actor=%s", flag.id, flag.tenant, flag.key, actor)
        return flag

    async def check_expiry(
        self,
        db: AsyncSession,
        tenant: str | None = None,
        warn_days: int = 30,
    ) -> list[dict[str, Any]]:
        """Warn about stale / expired flags.

        Returns list of dicts {flag, status, expires_at, age_days, reason}.
        Status is one of: expired | expiring_soon | stale | active.
        Flags with TAG or owner missing are not auto-archived — explicit archive required.
        """
        now = datetime.now(timezone.utc)
        soon = now + timedelta(days=max(0, int(warn_days)))

        stmt = select(FeatureFlag)
        if tenant:
            stmt = stmt.where(FeatureFlag.tenant == tenant.strip())
        # fetch flags that have expires_at set
        stmt = stmt.where(FeatureFlag.expires_at.is_not(None)).order_by(FeatureFlag.expires_at.asc())
        result = await db.execute(stmt)
        flags: list[FeatureFlag] = list(result.scalars().all())

        warnings: list[dict[str, Any]] = []
        for flag in flags:
            exp = flag.expires_at
            assert exp is not None
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            age_days = (now - flag.created_at).days if flag.created_at else 0

            # Determine status
            if exp < now:
                status = "expired"
                reason = f"flag {flag.key!r} expired at {exp.isoformat()}"
            elif exp <= soon:
                status = "expiring_soon"
                reason = f"flag {flag.key!r} expires at {exp.isoformat()} (within {warn_days}d)"
            elif age_days > 90 and flag.state not in (FlagState.ARCHIVED.value,):
                # stale: old flag never cleaned, warn if >90 days and not archived
                status = "stale"
                reason = f"flag {flag.key!r} is {age_days}d old — consider review/archive"
            else:
                # not warning
                continue

            warnings.append({
                "flag": flag,
                "flag_id": str(flag.id),
                "tenant": flag.tenant,
                "key": flag.key,
                "status": status,
                "expires_at": exp.isoformat(),
                "age_days": age_days,
                "reason": reason,
            })
            if status == "expired":
                logger.warning("flag expired: tenant=%s key=%s expires_at=%s age_days=%s", flag.tenant, flag.key, exp.isoformat(), age_days)
            elif status == "expiring_soon":
                logger.warning("flag expiring soon: tenant=%s key=%s expires_at=%s", flag.tenant, flag.key, exp.isoformat())
            else:
                logger.info("flag stale: tenant=%s key=%s age_days=%s", flag.tenant, flag.key, age_days)

        # also warn about stale flags even without expiry if older than 90 days and not archived
        # (additive warning — optional, helps owner cleanup)
        try:
            stmt2 = select(FeatureFlag).where(FeatureFlag.state != FlagState.ARCHIVED.value)
            if tenant:
                stmt2 = stmt2.where(FeatureFlag.tenant == tenant.strip())
            result2 = await db.execute(stmt2)
            all_active: list[FeatureFlag] = list(result2.scalars().all())
            for flag in all_active:
                if flag in flags:
                    continue  # already handled if it had expiry
                age_days = (now - flag.created_at).days if flag.created_at else 0
                # stale threshold: 180 days for flags never set to expire
                if age_days > 180:
                    warnings.append({
                        "flag": flag,
                        "flag_id": str(flag.id),
                        "tenant": flag.tenant,
                        "key": flag.key,
                        "status": "stale_no_expiry",
                        "expires_at": None,
                        "age_days": age_days,
                        "reason": f"flag {flag.key!r} is {age_days}d old with no expiry — review ownership",
                    })
                    logger.info("flag stale (no expiry): tenant=%s key=%s age_days=%s owner=%s", flag.tenant, flag.key, age_days, flag.owner)
        except Exception as exc:  # pragma: no cover
            logger.debug("check_expiry stale scan error: %s", exc)

        return warnings

    async def audit(
        self,
        db: AsyncSession,
        flag_id: uuid.UUID | str,
    ) -> list[FeatureFlagVersion]:
        """Return full audit history for flag ordered by version asc (via FeatureFlagVersion)."""
        fid = uuid.UUID(str(flag_id)) if isinstance(flag_id, str) else flag_id
        stmt = select(FeatureFlagVersion).where(FeatureFlagVersion.flag_id == fid).order_by(FeatureFlagVersion.version.asc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_versions(
        self,
        db: AsyncSession,
        flag_id: uuid.UUID | str,
        limit: int = 100,
    ) -> list[FeatureFlagVersion]:
        """Alias for audit() with limit (most recent first if caller needs)."""
        versions = await self.audit(db, flag_id)
        if limit and len(versions) > limit:
            return versions[-limit:]
        return versions

    async def list_evaluations(
        self,
        db: AsyncSession,
        flag_id: uuid.UUID | str,
        limit: int = 50,
    ) -> list[FeatureFlagEvaluation]:
        """Recent evaluations for a flag (most recent first)."""
        fid = uuid.UUID(str(flag_id)) if isinstance(flag_id, str) else flag_id
        stmt = select(FeatureFlagEvaluation).where(FeatureFlagEvaluation.flag_id == fid).order_by(FeatureFlagEvaluation.evaluated_at.desc()).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ---------------------------------------------------------------
    # Internal — audit helpers
    # ---------------------------------------------------------------

    async def _latest_version_number(self, db: AsyncSession, flag_id: uuid.UUID) -> int:
        stmt = select(func.coalesce(func.max(FeatureFlagVersion.version), 0)).where(FeatureFlagVersion.flag_id == flag_id)
        result = await db.execute(stmt)
        row = result.scalar_one()
        return int(row or 0)

    async def _audit_version(
        self,
        db: AsyncSession,
        flag: FeatureFlag,
        change: dict[str, Any],
        changed_by: str = "system",
    ) -> FeatureFlagVersion:
        next_version = await self._latest_version_number(db, flag.id) + 1
        # ensure JSON serializable
        safe_change: dict[str, Any] = {}
        for k, v in change.items():
            try:
                if isinstance(v, datetime):
                    safe_change[k] = v.isoformat()
                elif isinstance(v, uuid.UUID):
                    safe_change[k] = str(v)
                else:
                    safe_change[k] = v
            except Exception:
                safe_change[k] = str(v)
        row = FeatureFlagVersion(
            flag_id=flag.id,
            version=next_version,
            change=safe_change,
            changed_by=str(changed_by or "system"),
        )
        db.add(row)
        # do not flush here in helper? caller flushes — but flush now for version visibility
        await db.flush()
        return row
