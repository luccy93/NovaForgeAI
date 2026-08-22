"""ABAC engine — attribute-based access control with policy conditions."""
from __future__ import annotations
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from app.iam.constants import IAMPermission


class ABACCondition:
    def __init__(self, field: str, operator: str, value: Any, description: str = ""):
        self.field = field
        self.operator = operator
        self.value = value
        self.description = description

    def evaluate(self, context: dict) -> bool:
        actual = self._resolve_field(context, self.field)
        if self.operator == "equals":
            return actual == self.value
        elif self.operator == "not_equals":
            return actual != self.value
        elif self.operator == "in":
            return actual in self.value if isinstance(self.value, list) else False
        elif self.operator == "not_in":
            return actual not in self.value if isinstance(self.value, list) else False
        elif self.operator == "contains":
            if isinstance(actual, str) and isinstance(self.value, str):
                return self.value in actual
            if isinstance(actual, list):
                return self.value in actual
            return False
        elif self.operator == "greater_than":
            try:
                return float(actual) > float(self.value)
            except (TypeError, ValueError):
                return False
        elif self.operator == "less_than":
            try:
                return float(actual) < float(self.value)
            except (TypeError, ValueError):
                return False
        elif self.operator == "matches":
            if isinstance(actual, str) and isinstance(self.value, str):
                try:
                    return bool(re.search(self.value, actual))
                except re.error:
                    return False
            return False
        elif self.operator == "exists":
            return actual is not None
        elif self.operator == "not_exists":
            return actual is None
        return False

    def _resolve_field(self, context: dict, field_path: str) -> Any:
        parts = field_path.split(".")
        value = context
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and part.lstrip("-").isdigit():
                idx = int(part)
                value = value[idx] if 0 <= idx < len(value) else None
            else:
                return None
        return value

    def to_dict(self) -> dict:
        return {"field": self.field, "operator": self.operator, "value": self.value, "description": self.description}


class ABACPolicy:
    def __init__(self, policy_id: str, name: str, resource_type: str, action: str, effect: str = "allow", conditions: Optional[list[ABACCondition]] = None, denied_conditions: Optional[list[ABACCondition]] = None, priority: int = 0, description: str = ""):
        self.id = policy_id
        self.name = name
        self.resource_type = resource_type
        self.action = action
        self.effect = effect
        self.conditions = conditions or []
        self.denied_conditions = denied_conditions or []
        self.priority = priority
        self.description = description

    def evaluate(self, context: dict) -> dict:
        for deny_cond in self.denied_conditions:
            if deny_cond.evaluate(context):
                return {"matched": True, "decision": "denied", "policy_id": self.id, "policy_name": self.name, "reason": f"Deny condition met: {deny_cond.description or deny_cond.field}", "condition_details": [d.to_dict() for d in self.denied_conditions]}

        if not self.conditions:
            return {"matched": True, "decision": self.effect, "policy_id": self.id, "policy_name": self.name, "reason": "No conditions, policy matches by default"}

        passed = 0
        details = []
        for cond in self.conditions:
            result = cond.evaluate(context)
            details.append({"field": cond.field, "operator": cond.operator, "passed": result})
            if result:
                passed += 1

        all_passed = passed == len(self.conditions)
        return {"matched": all_passed, "decision": self.effect if all_passed else "not_applicable", "policy_id": self.id, "policy_name": self.name, "constraints_evaluated": len(self.conditions), "constraints_passed": passed, "details": details}

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "resource_type": self.resource_type, "action": self.action, "effect": self.effect, "conditions": [c.to_dict() for c in self.conditions], "denied_conditions": [c.to_dict() for c in self.denied_conditions], "priority": self.priority, "description": self.description}


class ABACEngine:
    def __init__(self):
        self._policies: dict[str, ABACPolicy] = {}
        self._evaluation_log: list[dict] = []

    def create_policy(self, name: str, resource_type: str, action: str, effect: str = "allow", conditions: Optional[list[dict]] = None, denied_conditions: Optional[list[dict]] = None, priority: int = 0, description: str = "") -> dict:
        policy_id = str(uuid.uuid4())
        conds = [ABACCondition(**c) for c in (conditions or [])]
        deny_conds = [ABACCondition(**c) for c in (denied_conditions or [])]
        policy = ABACPolicy(policy_id, name, resource_type, action, effect, conds, deny_conds, priority, description)
        self._policies[policy_id] = policy
        return policy.to_dict()

    def evaluate(self, resource_type: str, action: str, context: dict) -> dict:
        matching_policies = [p for p in self._policies.values() if p.resource_type == resource_type and p.action == action]
        matching_policies.sort(key=lambda p: p.priority, reverse=True)
        if not matching_policies:
            return {"decision": "not_applicable", "reason": "No matching ABAC policies", "policies_evaluated": 0, "matched_policies": []}
        results = []
        for policy in matching_policies:
            result = policy.evaluate(context)
            results.append(result)
            if result["decision"] == "denied":
                self._evaluation_log.append({"resource_type": resource_type, "action": action, "decision": "denied", "policy_id": policy.id, "time": datetime.now(timezone.utc).isoformat()})
                return {"decision": "denied", "reason": result.get("reason", ""), "policy_id": policy.id, "policies_evaluated": len(results), "matched_policies": [p.policy_id for p in results if p.get("matched")] if False else [r["policy_id"] for r in results if r.get("matched")]}
        allowed_results = [r for r in results if r.get("matched") and r["decision"] == "allow"]
        if allowed_results:
            self._evaluation_log.append({"resource_type": resource_type, "action": action, "decision": "allowed", "time": datetime.now(timezone.utc).isoformat()})
            return {"decision": "allowed", "policy_id": allowed_results[0]["policy_id"], "policies_evaluated": len(results), "matched_policies": [r["policy_id"] for r in results if r.get("matched")]}
        return {"decision": "not_applicable", "policies_evaluated": len(results), "matched_policies": []}

    def get_policy(self, policy_id: str) -> Optional[dict]:
        p = self._policies.get(policy_id)
        return p.to_dict() if p else None

    def list_policies(self, resource_type: Optional[str] = None, action: Optional[str] = None) -> list[dict]:
        policies = list(self._policies.values())
        if resource_type:
            policies = [p for p in policies if p.resource_type == resource_type]
        if action:
            policies = [p for p in policies if p.action == action]
        return [p.to_dict() for p in policies]

    def delete_policy(self, policy_id: str) -> bool:
        return self._policies.pop(policy_id, None) is not None

    def simulate(self, resource_type: str, action: str, context: dict) -> dict:
        result = self.evaluate(resource_type, action, context)
        result["simulation"] = True
        result["context"] = context
        return result

    def get_evaluation_log(self, limit: int = 100) -> list[dict]:
        return self._evaluation_log[-limit:]

    def get_stats(self) -> dict:
        return {"total_policies": len(self._policies), "total_evaluations": len(self._evaluation_log)}


abac_engine = ABACEngine()
