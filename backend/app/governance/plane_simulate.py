"""Policy simulation — Volume 71 Commit 1.

Evaluates hypothetical requests (single or batch) against current or
proposed policy versions without changing production state. Simulation
never flushes, never emits side-effect events, and never executes
actions. Supports before/after comparison and affected-resource
summaries.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_bindings import resolve_chain
from app.governance.plane_common import (
    SCOPE_TYPES,
    ValidationError,
    _as_uuid,
    _utcnow,
    sanitize_context,
)
from app.governance.plane_engine import match_condition, resolve_decision
from app.governance.plane_policies import get_active_version, list_versions

MAX_BATCH = 100


async def _overlay_versions(db: AsyncSession, tenant: str, proposed: Optional[dict]) -> dict:
    """Map policy_id -> version dict, overlaying a proposed version draft."""
    overlay: dict[str, dict] = {}
    if proposed:
        policy_id = str(proposed.get("policy_id") or "")
        rules = proposed.get("rules")
        if not policy_id or not isinstance(rules, list):
            raise ValidationError("proposed version requires policy_id and rules list")
        from app.governance.plane_policies import validate_rules
        overlay[policy_id] = {
            "id": "proposed",
            "policy_id": policy_id,
            "version": proposed.get("version", 0),
            "rules": validate_rules(rules),
            "default_effect": proposed.get("default_effect", "deny"),
            "status": "PROPOSED",
        }
    return overlay


async def simulate_one(
    db: AsyncSession, tenant: str, *,
    scope_type: str, scope_value: str = "", operation: str = "",
    context: Optional[dict] = None, proposed: Optional[dict] = None,
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    if scope_type not in SCOPE_TYPES:
        raise ValidationError(f"invalid scope_type: {scope_type!r}")
    clean = sanitize_context(context)
    overlay = await _overlay_versions(db, tenant, proposed)
    chain = await resolve_chain(db, tenant, scope_type, scope_value or "")
    matched: list[dict] = []
    default_effect = "deny"
    for binding in chain:
        policy_key = binding["policy_id"]
        if policy_key in overlay:
            version = overlay[policy_key]
        else:
            version = await get_active_version(db, tenant, binding["policy_id"])
            if version is None:
                continue
        default_effect = version.get("default_effect", "deny")
        for index, rule in enumerate(version.get("rules") or []):
            try:
                hit = match_condition(rule["condition"], clean)
            except ValidationError:
                continue
            if not hit:
                continue
            matched.append({
                "effect": rule["effect"], "priority": int(rule.get("priority", 0)),
                "depth": binding["depth"], "mandatory": bool(binding.get("mandatory")),
                "policy_id": binding["policy_id"], "version_id": version["id"],
                "binding_id": binding["id"], "rule_index": index,
                "rule_name": rule.get("name", f"rule-{index}"),
                "obligations": rule.get("obligations") or [],
            })
    resolution = resolve_decision(matched, default_effect=default_effect)
    winner = resolution.get("winner") or (resolution.get("matched") or [{}])[0] if resolution.get("matched") else {}
    return {
        "decision": resolution["decision"],
        "reason": resolution.get("reason", ""),
        "policy_id": winner.get("policy_id"),
        "version_id": winner.get("version_id"),
        "binding_id": winner.get("binding_id"),
        "rule_index": winner.get("rule_index"),
        "priority": int(winner.get("priority", 0)),
        "obligations": list(resolution.get("obligations", [])),
        "scope_type": scope_type,
        "scope_value": scope_value or "",
        "simulated_at": _utcnow().isoformat(),
        "side_effects": False,
    }


async def simulate_batch(
    db: AsyncSession, tenant: str, requests: list, *,
    proposed: Optional[dict] = None,
) -> dict:
    if not isinstance(requests, list) or not requests:
        raise ValidationError("requests must be a non-empty list")
    if len(requests) > MAX_BATCH:
        raise ValidationError(f"batch too large (max {MAX_BATCH})")
    results = []
    for item in requests:
        if not isinstance(item, dict):
            raise ValidationError("each request must be an object")
        results.append(await simulate_one(
            db, tenant, scope_type=item.get("scope_type", "tenant"),
            scope_value=item.get("scope_value", ""), operation=item.get("operation", ""),
            context=item.get("context"), proposed=proposed))
    summary: dict[str, int] = {}
    for result in results:
        summary[result["decision"]] = summary.get(result["decision"], 0) + 1
    return {"items": results, "total": len(results), "summary": summary}


async def compare_versions(
    db: AsyncSession, tenant: str, requests: list, *, proposed: dict,
) -> dict:
    """Before/after comparison of current vs proposed policy version."""
    before = await simulate_batch(db, tenant, requests)
    after = await simulate_batch(db, tenant, requests, proposed=proposed)
    changes = []
    for b, a in zip(before["items"], after["items"]):
        if b["decision"] != a["decision"]:
            changes.append({
                "scope_type": a["scope_type"], "scope_value": a["scope_value"],
                "before": b["decision"], "after": a["decision"],
                "reason": a["reason"],
            })
    affected = sorted({(c["scope_type"], c["scope_value"]) for c in changes})
    return {"before_summary": before["summary"], "after_summary": after["summary"],
            "changes": changes, "changed_count": len(changes),
            "affected_resources": [{"scope_type": s, "scope_value": v} for s, v in affected]}
