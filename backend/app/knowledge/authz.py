from __future__ import annotations

import logging

log = logging.getLogger(__name__)

CLASSIFICATION_LEVELS: dict[str, int] = {
    "PUBLIC": 0,
    "INTERNAL": 1,
    "CONFIDENTIAL": 2,
    "RESTRICTED": 3,
}

_REVERSE_LEVELS: dict[int, str] = {v: k for k, v in CLASSIFICATION_LEVELS.items()}


def get_user_clearance(user) -> int:
    """Extract max classification level a user can access. Defaults to INTERNAL (1)."""
    try:
        if user is None:
            return 1

        raw = getattr(user, "classification_clearance", None)
        if raw is not None:
            if isinstance(raw, int):
                return max(0, min(3, raw))
            level = CLASSIFICATION_LEVELS.get(str(raw).upper(), None)
            if level is not None:
                return level

        role = getattr(user, "role", None)
        if role is not None:
            role_str = str(role).upper()
            if role_str in ("ADMIN", "SUPERADMIN", "SUPER_ADMIN"):
                return 3
            if role_str in ("MANAGER", "LEAD"):
                return 2
            if role_str in ("USER", "MEMBER", "VIEWER"):
                return 1

        return 1
    except Exception:
        log.debug("Failed to determine user clearance, defaulting to INTERNAL (1)", exc_info=True)
        return 1


def is_authorized(result: dict, user_clearance: int) -> bool:
    """Check if a result's classification is within the user's clearance level. Fail-open."""
    try:
        classification = str(result.get("classification", "INTERNAL")).upper()
        level = CLASSIFICATION_LEVELS.get(classification, 1)
        return level <= user_clearance
    except Exception:
        return True


async def filter_authorized(results: list[dict], user) -> list[dict]:
    """Filter a result list to only authorized items. Fail-open on errors."""
    try:
        clearance = get_user_clearance(user)
        return [r for r in results if is_authorized(r, clearance)]
    except Exception:
        log.debug("Authorization filter failed, returning all results (fail-open)", exc_info=True)
        return results


async def check_tenant_access(tenant: str, user) -> bool:
    """Verify user belongs to the given tenant. Fail-open."""
    try:
        if user is None or tenant is None:
            return True

        user_org = getattr(user, "organization_id", None)
        if user_org is not None and str(user_org) == str(tenant):
            return True

        user_id = getattr(user, "id", None)
        if user_id is not None and str(user_id) == str(tenant):
            return True

        user_tenants = getattr(user, "tenants", None)
        if user_tenants and hasattr(user_tenants, "__contains__"):
            return str(tenant) in user_tenants

        return False
    except Exception:
        log.debug("Tenant access check failed for tenant %s, returning True (fail-open)", tenant, exc_info=True)
        return True


def apply_classification_filter(query_filters: dict, user_clearance: int) -> dict:
    """Add classification <= max_level to query filters. Returns modified filters dict."""
    try:
        modified = dict(query_filters) if query_filters else {}
        max_class = _REVERSE_LEVELS.get(user_clearance, "INTERNAL")
        modified["classification_max"] = max_class
        modified["classification_max_level"] = user_clearance
        return modified
    except Exception:
        log.debug("Failed to apply classification filter, returning original filters", exc_info=True)
        return dict(query_filters) if query_filters else {}
