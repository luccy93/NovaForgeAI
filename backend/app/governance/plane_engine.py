"""Deterministic policy-as-code evaluator — Volume 71 Commit 1.

Restricted declarative conditions only. No eval/exec/compile, no SQL,
no shell, no dynamic imports, no recursion. Unknown operators, fields
or shapes raise ValidationError instead of guessing.

Conflict resolution (deterministic):
1. organization mandatory deny rules always win;
2. otherwise any explicit deny wins over allow;
3. highest priority wins within an effect;
4. most-specific scope wins ties;
5. default deny (fail-safe).
"""

from __future__ import annotations

from typing import Any, Optional

from app.governance.plane_common import (
    CONDITION_OPS,
    CONTEXT_FIELDS,
    DECISIONS,
    EFFECTS,
    MAX_CONDITION_DEPTH,
    MAX_RULES,
    ValidationError,
)

RULE_EFFECTS = EFFECTS


def validate_condition(condition: dict, depth: int = 0) -> dict:
    if not isinstance(condition, dict):
        raise ValidationError("condition must be an object")
    if depth > MAX_CONDITION_DEPTH:
        raise ValidationError("condition nesting too deep")
    if "all" in condition or "any" in condition:
        key = "all" if "all" in condition else "any"
        branches = condition[key]
        if not isinstance(branches, list) or not branches:
            raise ValidationError(f"'{key}' requires a non-empty list")
        if len(branches) > MAX_RULES:
            raise ValidationError("too many condition branches")
        return {key: [validate_condition(branch, depth + 1) for branch in branches]}
    field = condition.get("field")
    op = condition.get("op")
    if field not in CONTEXT_FIELDS:
        raise ValidationError(f"unknown condition field: {field!r}")
    if op not in CONDITION_OPS:
        raise ValidationError(f"unknown condition operator: {op!r}")
    if op in ("exists", "not_exists") and "value" in condition:
        raise ValidationError(f"operator '{op}' takes no value")
    if op not in ("exists", "not_exists") and "value" not in condition:
        raise ValidationError(f"operator '{op}' requires a value")
    value = condition.get("value")
    if op in ("in", "not_in") and not isinstance(value, list):
        raise ValidationError(f"operator '{op}' requires a list value")
    if isinstance(value, (dict, set)):
        raise ValidationError("condition values must be scalars or scalar lists")
    return {"field": field, "op": op, **({"value": value} if "value" in condition else {})}


def validate_rule(rule: dict, index: int) -> dict:
    if not isinstance(rule, dict):
        raise ValidationError(f"rule {index} must be an object")
    effect = rule.get("effect")
    if effect not in RULE_EFFECTS:
        raise ValidationError(f"rule {index} has invalid effect: {effect!r}")
    if "condition" not in rule:
        raise ValidationError(f"rule {index} requires a condition")
    condition = validate_condition(rule["condition"])
    try:
        priority = int(rule.get("priority", 0))
    except (TypeError, ValueError):
        raise ValidationError(f"rule {index} has invalid priority")
    if not (-1000000 <= priority <= 1000000):
        raise ValidationError(f"rule {index} priority out of range")
    obligations = rule.get("obligations") or []
    if not isinstance(obligations, list) or any(not isinstance(o, str) for o in obligations):
        raise ValidationError(f"rule {index} obligations must be string list")
    name = str(rule.get("name") or f"rule-{index}")[:128]
    return {"name": name, "effect": effect, "condition": condition,
            "priority": priority, "obligations": obligations[:10]}


def _match_leaf(condition: dict, context: dict) -> bool:
    actual = context.get(condition["field"])
    op = condition["op"]
    if op == "exists":
        return actual is not None and actual != ""
    if op == "not_exists":
        return actual is None or actual == ""
    expected = condition.get("value")
    if op == "equals":
        return actual == expected
    if op == "not_equals":
        return actual != expected
    if op == "in":
        return actual in (expected or [])
    if op == "not_in":
        return actual not in (expected or [])
    if op == "contains":
        try:
            return expected in (actual or [])
        except TypeError:
            return str(expected) in str(actual or "")
    if op == "greater_than":
        try:
            return float(actual) > float(expected)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
    if op == "less_than":
        try:
            return float(actual) < float(expected)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
    return False


def match_condition(condition: dict, context: dict) -> bool:
    if "all" in condition:
        return all(match_condition(branch, context) for branch in condition["all"])
    if "any" in condition:
        return any(match_condition(branch, context) for branch in condition["any"])
    return _match_leaf(condition, context)


def resolve_decision(matched: list[dict], *, default_effect: str = "deny") -> dict:
    """Deterministic conflict resolution over matched rule entries.

    Each entry: {effect, priority, depth, mandatory, policy_id,
    version_id, binding_id, rule_index, rule_name, obligations}.
    """
    if not matched:
        return {"decision": "DENY" if default_effect == "deny" else "ALLOW",
                "matched": [], "reason": "no rules matched; default effect applied"}
    mandatory_denies = [m for m in matched if m.get("mandatory") and m["effect"] == "deny"]
    if mandatory_denies:
        winner = max(mandatory_denies, key=lambda m: (m["priority"], m["depth"]))
        return {"decision": "DENY", "matched": [winner], "winner": winner,
                "reason": "organization mandatory deny"}
    denies = [m for m in matched if m["effect"] == "deny"]
    if denies:
        winner = max(denies, key=lambda m: (m["priority"], m["depth"]))
        return {"decision": "DENY", "matched": [winner], "winner": winner,
                "reason": f"deny rule '{winner['rule_name']}' matched"}
    allows = [m for m in matched if m["effect"] == "allow"]
    if allows:
        winner = max(allows, key=lambda m: (m["priority"], m["depth"]))
        obligations = sorted({o for m in matched for o in (m.get("obligations") or [])})
        return {"decision": "ALLOW", "matched": [winner], "winner": winner,
                "obligations": obligations,
                "reason": f"allow rule '{winner['rule_name']}' matched"}
    requirers = [m for m in matched if m["effect"] == "require_approval"]
    if requirers:
        winner = max(requirers, key=lambda m: (m["priority"], m["depth"]))
        return {"decision": "REQUIRE_APPROVAL", "matched": [winner], "winner": winner,
                "reason": f"approval rule '{winner['rule_name']}' matched"}
    return {"decision": "DENY", "matched": [], "reason": "no allow rules matched"}
